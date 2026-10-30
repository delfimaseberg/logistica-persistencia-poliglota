-- 010: proveedores y operadores logísticos.
--
-- Aditiva e idempotente. No crea operadores ni asigna operadores a vehículos
-- o tramos existentes: vehiculo.empresa_operadora queda como texto histórico
-- (no se borra ni se interpreta) y los registros previos quedan con
-- id_operador NULL hasta que alguien los asigne explícitamente.

BEGIN;

CREATE TABLE IF NOT EXISTS operador_logistico (
    id_operador BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    razon_social VARCHAR(150) NOT NULL,
    cuit VARCHAR(13) NOT NULL,
    email VARCHAR(150) NOT NULL,
    telefono VARCHAR(30),
    direccion VARCHAR(255),
    pais VARCHAR(80) NOT NULL,
    -- Especialidad: uno o más medios de transporte (mismos valores que
    -- tramo.medio_transporte).
    modalidades VARCHAR(10)[] NOT NULL,
    estado VARCHAR(10) NOT NULL DEFAULT 'ACTIVO',
    fecha_alta TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fecha_baja TIMESTAMPTZ,
    CONSTRAINT uq_operador_cuit UNIQUE (cuit),
    CONSTRAINT chk_operador_cuit_formato
        CHECK (cuit ~ '^[0-9]{2}-[0-9]{8}-[0-9]$'),
    CONSTRAINT chk_operador_modalidades
        CHECK (
            cardinality(modalidades) > 0
            AND modalidades <@ ARRAY['Terrestre', 'Marítimo', 'Aéreo']::VARCHAR(10)[]
        ),
    CONSTRAINT chk_operador_estado CHECK (estado IN ('ACTIVO', 'INACTIVO')),
    -- Baja lógica: un inactivo siempre tiene fecha de baja y un activo no.
    CONSTRAINT chk_operador_baja CHECK (
        (estado = 'ACTIVO' AND fecha_baja IS NULL)
        OR (estado = 'INACTIVO' AND fecha_baja IS NOT NULL)
    )
);

CREATE TABLE IF NOT EXISTS proveedor (
    id_proveedor BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    razon_social VARCHAR(150) NOT NULL,
    cuit VARCHAR(13) NOT NULL,
    email VARCHAR(150) NOT NULL,
    telefono VARCHAR(30),
    direccion VARCHAR(255),
    pais VARCHAR(80) NOT NULL,
    rubro VARCHAR(20) NOT NULL,
    estado VARCHAR(10) NOT NULL DEFAULT 'ACTIVO',
    fecha_alta TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fecha_baja TIMESTAMPTZ,
    CONSTRAINT uq_proveedor_cuit UNIQUE (cuit),
    CONSTRAINT chk_proveedor_cuit_formato
        CHECK (cuit ~ '^[0-9]{2}-[0-9]{8}-[0-9]$'),
    CONSTRAINT chk_proveedor_rubro CHECK (
        rubro IN ('CONTENEDORES', 'SENSORES', 'SEGUROS', 'MANTENIMIENTO', 'OTROS')
    ),
    CONSTRAINT chk_proveedor_estado CHECK (estado IN ('ACTIVO', 'INACTIVO')),
    CONSTRAINT chk_proveedor_baja CHECK (
        (estado = 'ACTIVO' AND fecha_baja IS NULL)
        OR (estado = 'INACTIVO' AND fecha_baja IS NOT NULL)
    )
);

-- Operador que opera el vehículo (opcional) y operador que realizó el tramo.
-- El del tramo se copia del vehículo al registrarlo, para que el tramo
-- conserve quién lo hizo aunque el vehículo cambie de operador después.
ALTER TABLE vehiculo ADD COLUMN IF NOT EXISTS id_operador BIGINT;
ALTER TABLE tramo ADD COLUMN IF NOT EXISTS id_operador BIGINT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_vehiculo_operador'
          AND conrelid = 'vehiculo'::regclass
    ) THEN
        ALTER TABLE vehiculo ADD CONSTRAINT fk_vehiculo_operador
            FOREIGN KEY (id_operador) REFERENCES operador_logistico(id_operador);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_tramo_operador'
          AND conrelid = 'tramo'::regclass
    ) THEN
        ALTER TABLE tramo ADD CONSTRAINT fk_tramo_operador
            FOREIGN KEY (id_operador) REFERENCES operador_logistico(id_operador);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_vehiculo_operador ON vehiculo (id_operador);
CREATE INDEX IF NOT EXISTS idx_tramo_operador ON tramo (id_operador);

COMMENT ON COLUMN vehiculo.empresa_operadora IS
    'Histórico: texto libre anterior a la migración 010. No se escribe más; '
    'el operador vigente es vehiculo.id_operador.';

-- El operador de un tramo debe tener la modalidad del medio del tramo.
-- Solo se dispara cuando cambian esas columnas, así que no afecta otras
-- actualizaciones de tramos históricos (por ejemplo, distancia_km).
CREATE OR REPLACE FUNCTION validar_modalidad_operador_tramo()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.id_operador IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM operador_logistico o
        WHERE o.id_operador = NEW.id_operador
          AND NEW.medio_transporte = ANY (o.modalidades)
    ) THEN
        RAISE EXCEPTION
            'El operador % no tiene la modalidad % del tramo.',
            NEW.id_operador, NEW.medio_transporte
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_tramo_modalidad_operador ON tramo;
CREATE TRIGGER trg_tramo_modalidad_operador
    BEFORE INSERT OR UPDATE OF id_operador, medio_transporte ON tramo
    FOR EACH ROW EXECUTE FUNCTION validar_modalidad_operador_tramo();

COMMIT;
