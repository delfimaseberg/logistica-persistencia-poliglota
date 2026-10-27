-- Esquema aditivo para tarifas aprobadas y facturación trazable.
-- No inserta tarifas, códigos de moneda ni configuración fiscal.

BEGIN;

CREATE TABLE IF NOT EXISTS configuracion_fiscal (
    id_configuracion_fiscal BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    codigo VARCHAR(40) NOT NULL,
    version INTEGER NOT NULL,
    descripcion TEXT NOT NULL,
    tratamiento TEXT NOT NULL,
    tasa NUMERIC(12,6),
    vigente_desde DATE NOT NULL,
    vigente_hasta DATE,
    referencia_aprobacion TEXT NOT NULL,
    aprobado_por BIGINT NOT NULL,
    aprobado_en TIMESTAMPTZ NOT NULL,
    activa BOOLEAN NOT NULL,
    CONSTRAINT uq_config_fiscal_codigo_version UNIQUE (codigo, version),
    CONSTRAINT fk_config_fiscal_aprobador
        FOREIGN KEY (aprobado_por) REFERENCES usuario(id_usuario),
    CONSTRAINT chk_config_fiscal_version CHECK (version > 0),
    CONSTRAINT chk_config_fiscal_tasa CHECK (tasa IS NULL OR tasa >= 0),
    CONSTRAINT chk_config_fiscal_vigencia
        CHECK (vigente_hasta IS NULL OR vigente_hasta >= vigente_desde)
);

CREATE TABLE IF NOT EXISTS tarifa_envio (
    id_tarifa BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_envio BIGINT NOT NULL,
    version INTEGER NOT NULL,
    importe_base NUMERIC(14,2) NOT NULL,
    importe_impuestos NUMERIC(14,2) NOT NULL,
    importe_total NUMERIC(14,2) NOT NULL,
    moneda VARCHAR(3) NOT NULL,
    id_configuracion_fiscal BIGINT NOT NULL,
    tratamiento_impositivo TEXT NOT NULL,
    tasa_impositiva NUMERIC(12,6),
    estado VARCHAR(20) NOT NULL,
    referencia_aprobacion TEXT,
    aprobado_por BIGINT,
    aprobado_en TIMESTAMPTZ,
    creado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_tarifa_envio
        FOREIGN KEY (id_envio) REFERENCES envio(id_envio),
    CONSTRAINT fk_tarifa_config_fiscal
        FOREIGN KEY (id_configuracion_fiscal)
        REFERENCES configuracion_fiscal(id_configuracion_fiscal),
    CONSTRAINT fk_tarifa_aprobador
        FOREIGN KEY (aprobado_por) REFERENCES usuario(id_usuario),
    CONSTRAINT uq_tarifa_envio_version UNIQUE (id_envio, version),
    CONSTRAINT chk_tarifa_version CHECK (version > 0),
    CONSTRAINT chk_tarifa_importes
        CHECK (importe_base >= 0 AND importe_impuestos >= 0 AND importe_total > 0),
    CONSTRAINT chk_tarifa_estado
        CHECK (estado IN ('BORRADOR', 'APROBADA', 'REEMPLAZADA')),
    CONSTRAINT chk_tarifa_aprobacion
        CHECK (
            estado <> 'APROBADA'
            OR (referencia_aprobacion IS NOT NULL
                AND aprobado_por IS NOT NULL
                AND aprobado_en IS NOT NULL)
        )
);

CREATE TABLE IF NOT EXISTS tarifa_envio_auditoria (
    id_evento BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_tarifa BIGINT NOT NULL,
    estado_anterior VARCHAR(20),
    estado_nuevo VARCHAR(20) NOT NULL,
    motivo TEXT NOT NULL,
    usuario_id BIGINT NOT NULL,
    ocurrido_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_tarifa_auditoria_tarifa
        FOREIGN KEY (id_tarifa) REFERENCES tarifa_envio(id_tarifa),
    CONSTRAINT fk_tarifa_auditoria_usuario
        FOREIGN KEY (usuario_id) REFERENCES usuario(id_usuario)
);

ALTER TABLE factura
    ADD COLUMN IF NOT EXISTS id_envio BIGINT,
    ADD COLUMN IF NOT EXISTS id_tarifa BIGINT,
    ADD COLUMN IF NOT EXISTS evento_entrega_id TEXT,
    ADD COLUMN IF NOT EXISTS fecha_entrega TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS origen_emision VARCHAR(20),
    ADD COLUMN IF NOT EXISTS moneda VARCHAR(3),
    ADD COLUMN IF NOT EXISTS importe_base NUMERIC(14,2),
    ADD COLUMN IF NOT EXISTS importe_impuestos NUMERIC(14,2),
    ADD COLUMN IF NOT EXISTS id_configuracion_fiscal BIGINT,
    ADD COLUMN IF NOT EXISTS tratamiento_impositivo TEXT,
    ADD COLUMN IF NOT EXISTS tasa_impositiva NUMERIC(12,6);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_factura_envio'
          AND conrelid = 'factura'::regclass
    ) THEN
        ALTER TABLE factura ADD CONSTRAINT fk_factura_envio
            FOREIGN KEY (id_envio) REFERENCES envio(id_envio);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_factura_tarifa'
          AND conrelid = 'factura'::regclass
    ) THEN
        ALTER TABLE factura ADD CONSTRAINT fk_factura_tarifa
            FOREIGN KEY (id_tarifa) REFERENCES tarifa_envio(id_tarifa);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_factura_config_fiscal'
          AND conrelid = 'factura'::regclass
    ) THEN
        ALTER TABLE factura ADD CONSTRAINT fk_factura_config_fiscal
            FOREIGN KEY (id_configuracion_fiscal)
            REFERENCES configuracion_fiscal(id_configuracion_fiscal);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_factura_automatica_completa'
          AND conrelid = 'factura'::regclass
    ) THEN
        ALTER TABLE factura ADD CONSTRAINT chk_factura_automatica_completa
            CHECK (
                origen_emision IS DISTINCT FROM 'AUTOMATICA'
                OR (id_envio IS NOT NULL
                    AND id_tarifa IS NOT NULL
                    AND evento_entrega_id IS NOT NULL
                    AND fecha_entrega IS NOT NULL
                    AND moneda IS NOT NULL
                    AND importe_base IS NOT NULL
                    AND importe_impuestos IS NOT NULL
                    AND id_configuracion_fiscal IS NOT NULL
                    AND tratamiento_impositivo IS NOT NULL)
            ) NOT VALID;
    END IF;
END $$;

DO $$
BEGIN
    IF EXISTS (
        SELECT id_envio
        FROM tarifa_envio
        WHERE estado = 'APROBADA'
        GROUP BY id_envio
        HAVING COUNT(*) > 1
    ) THEN
        RAISE EXCEPTION
            'Hay más de una tarifa aprobada para un envío; resolver antes de continuar';
    END IF;

    IF EXISTS (
        SELECT id_envio
        FROM factura
        WHERE id_envio IS NOT NULL
        GROUP BY id_envio
        HAVING COUNT(*) > 1
    ) THEN
        RAISE EXCEPTION
            'Hay facturas duplicadas por envío; resolver antes de continuar';
    END IF;

    IF EXISTS (
        SELECT evento_entrega_id
        FROM factura
        WHERE evento_entrega_id IS NOT NULL
        GROUP BY evento_entrega_id
        HAVING COUNT(*) > 1
    ) THEN
        RAISE EXCEPTION
            'Hay facturas duplicadas por evento de entrega; resolver antes de continuar';
    END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS uq_tarifa_envio_aprobada
    ON tarifa_envio (id_envio)
    WHERE estado = 'APROBADA';

CREATE UNIQUE INDEX IF NOT EXISTS uq_factura_original_envio
    ON factura (id_envio)
    WHERE id_envio IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_factura_evento_entrega
    ON factura (evento_entrega_id)
    WHERE evento_entrega_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS correccion_factura (
    id_correccion BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_factura_original BIGINT NOT NULL,
    tipo VARCHAR(20) NOT NULL,
    importe NUMERIC(14,2) NOT NULL,
    importe_base NUMERIC(14,2) NOT NULL,
    importe_impuestos NUMERIC(14,2) NOT NULL,
    moneda VARCHAR(3) NOT NULL,
    id_configuracion_fiscal BIGINT NOT NULL,
    tratamiento_impositivo TEXT NOT NULL,
    tasa_impositiva NUMERIC(12,6),
    motivo TEXT NOT NULL,
    referencia_aprobacion TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    solicitada_por BIGINT NOT NULL,
    aprobada_por BIGINT NOT NULL,
    aprobada_en TIMESTAMPTZ NOT NULL,
    registrada_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_correccion_factura_original
        FOREIGN KEY (id_factura_original) REFERENCES factura(id_factura),
    CONSTRAINT fk_correccion_config_fiscal
        FOREIGN KEY (id_configuracion_fiscal)
        REFERENCES configuracion_fiscal(id_configuracion_fiscal),
    CONSTRAINT fk_correccion_solicitante
        FOREIGN KEY (solicitada_por) REFERENCES usuario(id_usuario),
    CONSTRAINT fk_correccion_aprobador
        FOREIGN KEY (aprobada_por) REFERENCES usuario(id_usuario),
    CONSTRAINT chk_correccion_tipo CHECK (tipo IN ('CREDITO', 'DEBITO')),
    CONSTRAINT chk_correccion_importe CHECK (importe > 0)
);

CREATE TABLE IF NOT EXISTS auditoria_facturacion_periodica (
    id_evento BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_envio BIGINT,
    envio_id_reportado BIGINT,
    evento_entrega_id TEXT,
    resultado VARCHAR(20) NOT NULL,
    motivo TEXT NOT NULL,
    id_factura BIGINT,
    registrado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_auditoria_facturacion_envio
        FOREIGN KEY (id_envio) REFERENCES envio(id_envio),
    CONSTRAINT fk_auditoria_facturacion_factura
        FOREIGN KEY (id_factura) REFERENCES factura(id_factura),
    CONSTRAINT chk_auditoria_facturacion_resultado
        CHECK (resultado IN ('BLOQUEADA', 'ERROR', 'FACTURADA')),
    CONSTRAINT chk_auditoria_facturacion_envio_referido
        CHECK (id_envio IS NOT NULL OR envio_id_reportado IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_auditoria_facturacion_envio_fecha
    ON auditoria_facturacion_periodica (id_envio, registrado_en);

COMMIT;
