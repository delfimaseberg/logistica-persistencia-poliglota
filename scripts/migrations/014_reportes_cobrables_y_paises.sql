-- 014: reportes cobrables por cliente y países de origen/destino del envío.
--
-- Idempotente. No modifica facturas, pagos ni saldos. Los envíos existentes
-- quedan con país "sin dato" (NULL); los nuevos deben indicarlo.
-- Requiere 003-013.

BEGIN;

DO $$
BEGIN
    IF to_regclass('public.factura_detalle') IS NULL THEN
        RAISE EXCEPTION '014 requiere la migración 013';
    END IF;
END $$;

-- ------------------------------------------------------------------
-- Países de origen y destino del envío
-- ------------------------------------------------------------------

ALTER TABLE envio ADD COLUMN IF NOT EXISTS pais_origen VARCHAR(80);
ALTER TABLE envio ADD COLUMN IF NOT EXISTS pais_destino VARCHAR(80);

CREATE INDEX IF NOT EXISTS idx_envio_pais_destino ON envio (pais_destino);

-- Obligatorios para envíos nuevos (los anteriores a 014 quedan sin dato).
CREATE OR REPLACE FUNCTION exigir_paises_envio()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.pais_origen IS NULL OR btrim(NEW.pais_origen) = ''
       OR NEW.pais_destino IS NULL OR btrim(NEW.pais_destino) = '' THEN
        RAISE EXCEPTION 'Un envío nuevo debe indicar país de origen y de destino.'
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_envio_exige_paises ON envio;
CREATE TRIGGER trg_envio_exige_paises
    BEFORE INSERT ON envio
    FOR EACH ROW EXECUTE FUNCTION exigir_paises_envio();

-- Una vez cargado, el país no vuelve a quedar vacío.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_envio_paises_no_vacios' AND conrelid = 'envio'::regclass
    ) THEN
        ALTER TABLE envio ADD CONSTRAINT chk_envio_paises_no_vacios CHECK (
            (pais_origen IS NULL OR btrim(pais_origen) <> '')
            AND (pais_destino IS NULL OR btrim(pais_destino) <> '')
        );
    END IF;
END $$;

-- ------------------------------------------------------------------
-- Catálogo y precios de reportes cobrables
-- ------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS tipo_reporte (
    codigo VARCHAR(30) PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    descripcion TEXT NOT NULL,
    base_datos VARCHAR(60) NOT NULL,
    precio NUMERIC(14,2) NOT NULL,
    activo BOOLEAN NOT NULL DEFAULT TRUE,
    actualizado_por BIGINT REFERENCES usuario(id_usuario),
    actualizado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_tipo_reporte_precio CHECK (precio > 0)
);

-- Precios definidos por la empresa (ARS, sin IVA). Solo si no existen.
INSERT INTO tipo_reporte (codigo, nombre, descripcion, base_datos, precio)
VALUES
    ('INCIDENTES', 'Incidentes y alertas de mis envíos',
     'Incidentes de los envíos del cliente y alertas de sus contenedores.',
     'PostgreSQL + MongoDB', 15000),
    ('PUNTUALIDAD', 'Puntualidad de mis envíos',
     'Envíos a tiempo, tarde y demorados, con horas de diferencia y retrasos informados.',
     'PostgreSQL + MongoDB', 12000),
    ('OPERADORES', 'Operadores que llevaron mis contenedores',
     'Tramos y operadores logísticos de los contenedores del cliente.',
     'Neo4j + PostgreSQL', 10000),
    ('CONDICIONES_CARGA', 'Condiciones de la carga en viaje',
     'Temperatura, humedad, lecturas fuera de rango y recorrido GPS por contenedor.',
     'Cassandra + PostgreSQL', 25000)
ON CONFLICT (codigo) DO NOTHING;

-- ------------------------------------------------------------------
-- Reporte: solicitado -> generado -> facturado (o error)
-- ------------------------------------------------------------------

DO $$
BEGIN
    -- id_cliente se agrega obligatorio: solo se admite si la tabla está vacía
    -- o todas sus filas ya lo tienen.
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'reporte' AND column_name = 'id_cliente'
    ) THEN
        NULL;
    ELSIF EXISTS (SELECT 1 FROM reporte) THEN
        RAISE EXCEPTION 'reporte tiene filas sin cliente; completarlas antes de aplicar 014';
    END IF;
END $$;

ALTER TABLE reporte ADD COLUMN IF NOT EXISTS id_cliente BIGINT;
ALTER TABLE reporte ADD COLUMN IF NOT EXISTS parametros JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE reporte ADD COLUMN IF NOT EXISTS importe_base NUMERIC(14,2);
ALTER TABLE reporte ADD COLUMN IF NOT EXISTS fecha_solicitud TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE reporte ADD COLUMN IF NOT EXISTS archivo TEXT;
ALTER TABLE reporte ADD COLUMN IF NOT EXISTS filas INTEGER;
ALTER TABLE reporte ADD COLUMN IF NOT EXISTS hash_archivo VARCHAR(64);
ALTER TABLE reporte ADD COLUMN IF NOT EXISTS error TEXT;

ALTER TABLE reporte ALTER COLUMN id_cliente SET NOT NULL;
ALTER TABLE reporte ALTER COLUMN importe_base SET NOT NULL;
-- La fecha de generación se completa al generar.
ALTER TABLE reporte ALTER COLUMN fecha_generacion DROP NOT NULL;
ALTER TABLE reporte ALTER COLUMN fecha_generacion DROP DEFAULT;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conname = 'fk_reporte_cliente' AND conrelid = 'reporte'::regclass) THEN
        ALTER TABLE reporte ADD CONSTRAINT fk_reporte_cliente
            FOREIGN KEY (id_cliente) REFERENCES cliente(id_cliente);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conname = 'fk_reporte_tipo' AND conrelid = 'reporte'::regclass) THEN
        ALTER TABLE reporte ADD CONSTRAINT fk_reporte_tipo
            FOREIGN KEY (tipo) REFERENCES tipo_reporte(codigo);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conname = 'chk_reporte_estado' AND conrelid = 'reporte'::regclass) THEN
        ALTER TABLE reporte ADD CONSTRAINT chk_reporte_estado
            CHECK (estado IN ('SOLICITADO', 'GENERADO', 'FACTURADO', 'ERROR'));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conname = 'chk_reporte_generado_completo' AND conrelid = 'reporte'::regclass) THEN
        ALTER TABLE reporte ADD CONSTRAINT chk_reporte_generado_completo CHECK (
            estado NOT IN ('GENERADO', 'FACTURADO')
            OR (archivo IS NOT NULL AND hash_archivo IS NOT NULL
                AND fecha_generacion IS NOT NULL AND filas IS NOT NULL)
        );
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conname = 'chk_reporte_importe' AND conrelid = 'reporte'::regclass) THEN
        ALTER TABLE reporte ADD CONSTRAINT chk_reporte_importe CHECK (importe_base > 0);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_reporte_cliente_fecha
    ON reporte (id_cliente, fecha_solicitud);

-- ------------------------------------------------------------------
-- Factura de un reporte: mismo desglose que la de un envío
-- ------------------------------------------------------------------

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conname = 'chk_factura_reporte_completa' AND conrelid = 'factura'::regclass) THEN
        ALTER TABLE factura ADD CONSTRAINT chk_factura_reporte_completa CHECK (
            id_reporte IS NULL OR (
                origen_emision = 'REPORTE'
                AND moneda = 'ARS'
                AND importe_base IS NOT NULL
                AND importe_impuestos IS NOT NULL
                AND tasa_impositiva IS NOT NULL
                AND tratamiento_impositivo IS NOT NULL
                AND total = importe_base + importe_impuestos
            )
        );
    END IF;
END $$;

COMMIT;
