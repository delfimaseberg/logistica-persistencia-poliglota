-- 013: facturación a clientes por envío, fecha real de entrega y origen de
-- factura (envío o reporte).
--
-- Aditiva e idempotente. No modifica facturas, pagos ni saldos existentes:
-- las facturas históricas (sin envío ni reporte) quedan como están.
-- Requiere 003-012.

BEGIN;

DO $$
BEGIN
    IF to_regclass('public.regla_tarifaria_version') IS NULL
       OR to_regclass('public.reporte') IS NULL
       OR to_regclass('public.movimiento_cuenta_corriente') IS NULL THEN
        RAISE EXCEPTION '013 requiere las migraciones 003 a 012';
    END IF;
END $$;

-- ------------------------------------------------------------------
-- Fecha real de entrega
-- ------------------------------------------------------------------

ALTER TABLE envio ADD COLUMN IF NOT EXISTS fecha_entrega TIMESTAMPTZ;

DO $$
BEGIN
    -- No se inventan fechas: si hubiera envíos entregados sin fecha real,
    -- hay que completarlas a mano antes de aplicar esta migración.
    IF EXISTS (
        SELECT 1 FROM envio
        WHERE lower(btrim(estado)) = 'entregado' AND fecha_entrega IS NULL
    ) THEN
        RAISE EXCEPTION
            'Hay envíos Entregados sin fecha_entrega; completarlas antes de aplicar 013';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_envio_fecha_entrega'
          AND conrelid = 'envio'::regclass
    ) THEN
        -- Entregado <=> tiene fecha real de entrega, y no antes de crearse.
        ALTER TABLE envio ADD CONSTRAINT chk_envio_fecha_entrega CHECK (
            ((lower(btrim(estado)) = 'entregado') = (fecha_entrega IS NOT NULL))
            AND (fecha_entrega IS NULL OR fecha_entrega >= fecha_creacion)
        );
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_envio_fecha_entrega
    ON envio (fecha_entrega) WHERE fecha_entrega IS NOT NULL;

-- Entregado es un estado final: no cambia el estado, la fecha ni el cliente.
CREATE OR REPLACE FUNCTION proteger_envio_entregado()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF lower(btrim(OLD.estado)) = 'entregado' AND (
        NEW.estado IS DISTINCT FROM OLD.estado
        OR NEW.fecha_entrega IS DISTINCT FROM OLD.fecha_entrega
        OR NEW.id_cliente IS DISTINCT FROM OLD.id_cliente
    ) THEN
        RAISE EXCEPTION
            'El envío % está Entregado: su estado, fecha de entrega y cliente no cambian.',
            OLD.id_envio
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_envio_entregado_final ON envio;
CREATE TRIGGER trg_envio_entregado_final
    BEFORE UPDATE OF estado, fecha_entrega, id_cliente ON envio
    FOR EACH ROW EXECUTE FUNCTION proteger_envio_entregado();

-- ------------------------------------------------------------------
-- Factura: regla de precios usada y origen (envío o reporte)
-- ------------------------------------------------------------------

ALTER TABLE factura ADD COLUMN IF NOT EXISTS id_regla BIGINT;
ALTER TABLE factura ADD COLUMN IF NOT EXISTS id_reporte BIGINT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_factura_regla' AND conrelid = 'factura'::regclass
    ) THEN
        ALTER TABLE factura ADD CONSTRAINT fk_factura_regla
            FOREIGN KEY (id_regla) REFERENCES regla_tarifaria_version(id_regla);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_factura_reporte' AND conrelid = 'factura'::regclass
    ) THEN
        ALTER TABLE factura ADD CONSTRAINT fk_factura_reporte
            FOREIGN KEY (id_reporte) REFERENCES reporte(id_reporte);
    END IF;

    -- Como mucho un origen. Las históricas no tienen ninguno.
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_factura_un_origen' AND conrelid = 'factura'::regclass
    ) THEN
        ALTER TABLE factura ADD CONSTRAINT chk_factura_un_origen
            CHECK (num_nonnulls(id_envio, id_reporte) <= 1);
    END IF;

    -- NULL y MANUAL: históricas. AUTOMATICA: esquema 004 (sin uso).
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_factura_origen_emision' AND conrelid = 'factura'::regclass
    ) THEN
        ALTER TABLE factura ADD CONSTRAINT chk_factura_origen_emision
            CHECK (origen_emision IS NULL OR origen_emision IN (
                'MANUAL', 'AUTOMATICA', 'ENVIO_MANUAL', 'ENVIO_AUTOMATICA', 'REPORTE'
            ));
    END IF;

    -- Una factura de envío guarda la regla, el desglose con IVA y la entrega.
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_factura_envio_completa' AND conrelid = 'factura'::regclass
    ) THEN
        ALTER TABLE factura ADD CONSTRAINT chk_factura_envio_completa CHECK (
            id_envio IS NULL OR (
                id_regla IS NOT NULL
                AND origen_emision IN ('ENVIO_MANUAL', 'ENVIO_AUTOMATICA')
                AND moneda = 'ARS'
                AND importe_base IS NOT NULL
                AND importe_impuestos IS NOT NULL
                AND tasa_impositiva IS NOT NULL
                AND tratamiento_impositivo IS NOT NULL
                AND fecha_entrega IS NOT NULL
                AND total = importe_base + importe_impuestos
            )
        );
    END IF;
END $$;

-- Un envío ya tiene uq_factura_original_envio (004); lo mismo para reportes.
CREATE UNIQUE INDEX IF NOT EXISTS uq_factura_reporte
    ON factura (id_reporte) WHERE id_reporte IS NOT NULL;

-- Desde 013 no se emiten facturas sin origen (monto suelto). Solo al
-- insertar: las históricas siguen recibiendo pagos (UPDATE de estado).
CREATE OR REPLACE FUNCTION exigir_origen_factura()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.id_envio IS NULL AND NEW.id_reporte IS NULL THEN
        RAISE EXCEPTION
            'Una factura nueva debe corresponder a un envío o a un reporte.'
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_factura_requiere_origen ON factura;
CREATE TRIGGER trg_factura_requiere_origen
    BEFORE INSERT ON factura
    FOR EACH ROW EXECUTE FUNCTION exigir_origen_factura();

-- ------------------------------------------------------------------
-- Detalle de factura: base por envío y una línea por tramo (neto, sin IVA)
-- ------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS factura_detalle (
    id_detalle BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_factura BIGINT NOT NULL REFERENCES factura(id_factura),
    linea SMALLINT NOT NULL,
    concepto VARCHAR(10) NOT NULL,
    id_tramo BIGINT REFERENCES tramo(id_tramo),
    medio_transporte VARCHAR(20),
    descripcion VARCHAR(255) NOT NULL,
    importe NUMERIC(14,2) NOT NULL,
    CONSTRAINT uq_factura_detalle_linea UNIQUE (id_factura, linea),
    CONSTRAINT chk_factura_detalle_concepto
        CHECK (concepto IN ('BASE', 'TRAMO', 'REPORTE')),
    CONSTRAINT chk_factura_detalle_importe CHECK (importe >= 0),
    CONSTRAINT chk_factura_detalle_tramo CHECK (
        (concepto = 'TRAMO' AND id_tramo IS NOT NULL AND medio_transporte IS NOT NULL)
        OR (concepto <> 'TRAMO' AND id_tramo IS NULL)
    )
);

CREATE INDEX IF NOT EXISTS idx_factura_detalle_medio
    ON factura_detalle (medio_transporte) WHERE concepto = 'TRAMO';

COMMIT;
