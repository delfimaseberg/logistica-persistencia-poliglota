-- Datos de carga, distancias y reglas versionadas para calcular tarifas.
-- Requiere el esquema inicial y la migración 004. No carga valores comerciales.
-- Los campos fiscales quedan opcionales solo en BORRADOR; la aprobación exige
-- la configuración fiscal completa ya requerida por el flujo financiero.

BEGIN;

DO $$
BEGIN
    IF to_regclass('public.envio') IS NULL
       OR to_regclass('public.tramo') IS NULL
       OR to_regclass('public.tarifa_envio') IS NULL
       OR to_regclass('public.configuracion_fiscal') IS NULL THEN
        RAISE EXCEPTION '007 requiere el esquema base y la migración 004';
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS tipo_carga (
    codigo VARCHAR(40) PRIMARY KEY,
    descripcion VARCHAR(150) NOT NULL,
    activo BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS envio_carga (
    id_envio_carga BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_envio BIGINT NOT NULL REFERENCES envio(id_envio),
    tipo_carga VARCHAR(40) NOT NULL REFERENCES tipo_carga(codigo),
    peso_kg NUMERIC(14,3) NOT NULL CHECK (peso_kg > 0),
    fragil BOOLEAN NOT NULL,
    descripcion TEXT,
    registrado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_envio_carga_envio
    ON envio_carga (id_envio, id_envio_carga);

ALTER TABLE tramo
    ADD COLUMN IF NOT EXISTS distancia_km NUMERIC(14,3);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'tramo'::regclass
          AND conname = 'chk_tramo_distancia_km_positiva'
    ) THEN
        ALTER TABLE tramo ADD CONSTRAINT chk_tramo_distancia_km_positiva
            CHECK (distancia_km IS NULL OR distancia_km > 0);
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS regla_tarifaria_version (
    id_regla BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    codigo VARCHAR(60) NOT NULL,
    version INTEGER NOT NULL,
    moneda VARCHAR(3) NOT NULL,
    vigente_desde DATE NOT NULL,
    vigente_hasta DATE,
    estado VARCHAR(20) NOT NULL DEFAULT 'BORRADOR',
    referencia_aprobacion TEXT,
    aprobado_por BIGINT REFERENCES usuario(id_usuario),
    aprobado_en TIMESTAMPTZ,
    creada_por BIGINT NOT NULL REFERENCES usuario(id_usuario),
    creada_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_regla_tarifaria_codigo_version UNIQUE (codigo, version),
    CONSTRAINT chk_regla_tarifaria_version CHECK (version > 0),
    CONSTRAINT chk_regla_tarifaria_vigencia
        CHECK (vigente_hasta IS NULL OR vigente_hasta >= vigente_desde),
    CONSTRAINT chk_regla_tarifaria_estado
        CHECK (estado IN ('BORRADOR', 'APROBADA', 'REEMPLAZADA')),
    CONSTRAINT chk_regla_tarifaria_aprobacion
        CHECK (estado = 'BORRADOR' OR
               (referencia_aprobacion IS NOT NULL AND aprobado_por IS NOT NULL
                AND aprobado_en IS NOT NULL))
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_regla_tarifaria_aprobada_codigo
    ON regla_tarifaria_version (codigo)
    WHERE estado = 'APROBADA';

CREATE TABLE IF NOT EXISTS regla_tarifaria_componente (
    id_componente BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_regla BIGINT NOT NULL REFERENCES regla_tarifaria_version(id_regla),
    criterio VARCHAR(20) NOT NULL,
    selector VARCHAR(80),
    ambito VARCHAR(10) NOT NULL,
    base_calculo VARCHAR(20) NOT NULL,
    importe NUMERIC(18,6) NOT NULL CHECK (importe >= 0),
    CONSTRAINT chk_regla_componente_criterio
        CHECK (criterio IN ('BASE', 'PESO', 'DISTANCIA', 'PESO_DISTANCIA', 'CATEGORIA', 'FRAGIL', 'TRANSPORTE')),
    CONSTRAINT chk_regla_componente_ambito
        CHECK (ambito IN ('ENVIO', 'PARTIDA', 'TRAMO')),
    CONSTRAINT chk_regla_componente_base
        CHECK (base_calculo IN ('FIJO', 'POR_KG', 'POR_KM', 'POR_KG_KM')),
    CONSTRAINT chk_regla_componente_combinacion
        CHECK (
            (criterio = 'BASE' AND ambito = 'ENVIO' AND base_calculo = 'FIJO' AND selector IS NULL)
            OR (criterio = 'PESO' AND ambito = 'ENVIO' AND base_calculo = 'POR_KG' AND selector IS NULL)
            OR (criterio = 'DISTANCIA' AND ambito = 'ENVIO' AND base_calculo = 'POR_KM' AND selector IS NULL)
            OR (criterio = 'PESO_DISTANCIA' AND ambito = 'ENVIO' AND base_calculo = 'POR_KG_KM' AND selector IS NULL)
            OR (criterio = 'CATEGORIA' AND ambito = 'PARTIDA' AND base_calculo IN ('FIJO', 'POR_KG') AND selector IS NOT NULL)
            OR (criterio = 'FRAGIL' AND ambito = 'PARTIDA' AND base_calculo IN ('FIJO', 'POR_KG') AND selector = 'true')
            OR (criterio = 'TRANSPORTE' AND ambito = 'TRAMO' AND base_calculo IN ('FIJO', 'POR_KM') AND selector IS NOT NULL)
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_regla_componente_dimension
    ON regla_tarifaria_componente
       (id_regla, criterio, COALESCE(LOWER(selector), ''), ambito);

CREATE INDEX IF NOT EXISTS idx_regla_componente_regla
    ON regla_tarifaria_componente (id_regla, criterio);

CREATE TABLE IF NOT EXISTS regla_tarifaria_auditoria (
    id_evento BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_regla BIGINT NOT NULL REFERENCES regla_tarifaria_version(id_regla),
    estado_anterior VARCHAR(20),
    estado_nuevo VARCHAR(20) NOT NULL,
    motivo TEXT NOT NULL,
    usuario_id BIGINT NOT NULL REFERENCES usuario(id_usuario),
    ocurrido_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE tarifa_envio
    ADD COLUMN IF NOT EXISTS id_regla BIGINT REFERENCES regla_tarifaria_version(id_regla),
    ADD COLUMN IF NOT EXISTS detalle_calculo JSONB;

-- Solo los borradores pueden quedar pendientes de moneda/fiscalidad. Una
-- tarifa APROBADA debe satisfacer íntegramente la condición financiera.
ALTER TABLE tarifa_envio
    ALTER COLUMN importe_impuestos DROP NOT NULL,
    ALTER COLUMN importe_total DROP NOT NULL,
    ALTER COLUMN moneda DROP NOT NULL,
    ALTER COLUMN id_configuracion_fiscal DROP NOT NULL,
    ALTER COLUMN tratamiento_impositivo DROP NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'tarifa_envio'::regclass
          AND conname = 'chk_tarifa_aprobada_completa'
    ) THEN
        ALTER TABLE tarifa_envio ADD CONSTRAINT chk_tarifa_aprobada_completa
            CHECK (estado <> 'APROBADA' OR
                (id_regla IS NOT NULL AND detalle_calculo IS NOT NULL
                 AND importe_impuestos IS NOT NULL AND importe_total IS NOT NULL
                 AND moneda IS NOT NULL AND id_configuracion_fiscal IS NOT NULL
                 AND tratamiento_impositivo IS NOT NULL
                 AND referencia_aprobacion IS NOT NULL AND aprobado_por IS NOT NULL
                 AND aprobado_en IS NOT NULL)) NOT VALID;
    END IF;
END $$;

CREATE OR REPLACE FUNCTION proteger_regla_tarifaria_aprobada()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    v_id_regla BIGINT;
BEGIN
    IF TG_TABLE_NAME = 'regla_tarifaria_version' THEN
        IF OLD.estado <> 'BORRADOR' THEN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'Una versión aprobada de reglas es inmutable; cree otra versión.';
            END IF;
            IF (to_jsonb(NEW) - 'estado') IS DISTINCT FROM (to_jsonb(OLD) - 'estado') THEN
                RAISE EXCEPTION 'Una versión aprobada de reglas es inmutable; cree otra versión.';
            END IF;
            IF NOT (OLD.estado = 'APROBADA' AND NEW.estado = 'REEMPLAZADA') THEN
                RAISE EXCEPTION 'Solo se permite reemplazar una regla aprobada.';
            END IF;
        END IF;
        RETURN NEW;
    END IF;

    IF TG_OP = 'DELETE' THEN
        v_id_regla := OLD.id_regla;
    ELSE
        v_id_regla := NEW.id_regla;
    END IF;
    IF EXISTS (
        SELECT 1 FROM regla_tarifaria_version r
        WHERE r.id_regla = v_id_regla AND r.estado <> 'BORRADOR'
    ) THEN
        RAISE EXCEPTION 'No se pueden alterar componentes de una regla aprobada.';
    END IF;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_regla_tarifaria_inmutable
    ON regla_tarifaria_version;
CREATE TRIGGER trg_regla_tarifaria_inmutable
    BEFORE UPDATE OR DELETE ON regla_tarifaria_version
    FOR EACH ROW EXECUTE FUNCTION proteger_regla_tarifaria_aprobada();

DROP TRIGGER IF EXISTS trg_regla_tarifaria_componente_inmutable
    ON regla_tarifaria_componente;
CREATE TRIGGER trg_regla_tarifaria_componente_inmutable
    BEFORE INSERT OR UPDATE OR DELETE ON regla_tarifaria_componente
    FOR EACH ROW EXECUTE FUNCTION proteger_regla_tarifaria_aprobada();

COMMIT;
