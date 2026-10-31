-- 015: reglas de alerta configurables, reporte cobrable predictivo,
-- sensores inactivos al entregar, cierre de sesiones ajenas y países de los
-- envíos de prueba 2, 3 y 4.
--
-- Idempotente. No modifica facturas, pagos ni saldos. Requiere 003-014.
-- Antes de aplicar en la base principal se verifica aparte que la cantidad
-- de sensores a desactivar sea la esperada (ver procedimiento del día 3B).

BEGIN;

DO $$
BEGIN
    IF to_regclass('public.tipo_reporte') IS NULL THEN
        RAISE EXCEPTION '015 requiere la migración 014';
    END IF;
END $$;

-- ------------------------------------------------------------------
-- Reglas de alerta (umbrales que usa la detección)
-- ------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS regla_alerta (
    id_regla BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    variable VARCHAR(30) NOT NULL,
    limite VARCHAR(3) NOT NULL,
    valor NUMERIC(10,2) NOT NULL,
    severidad VARCHAR(10) NOT NULL,
    activa BOOLEAN NOT NULL DEFAULT TRUE,
    descripcion VARCHAR(200),
    creada_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    actualizada_por BIGINT REFERENCES usuario(id_usuario),
    actualizada_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_regla_variable CHECK (variable IN (
        'temperatura', 'humedad', 'vibracion', 'bateria',
        'horas_sin_transmision', 'salto_temperatura', 'lecturas_congeladas')),
    CONSTRAINT chk_regla_limite CHECK (limite IN ('MIN', 'MAX')),
    CONSTRAINT chk_regla_severidad CHECK (
        severidad IN ('Baja', 'Media', 'Alta', 'Crítica')),
    -- Valores físicamente posibles para cada variable.
    CONSTRAINT chk_regla_rango CHECK (
        (variable = 'temperatura' AND valor BETWEEN -50 AND 90)
        OR (variable IN ('humedad', 'bateria') AND valor BETWEEN 0 AND 100)
        OR (variable = 'vibracion' AND valor BETWEEN 0 AND 1000)
        OR (variable = 'horas_sin_transmision' AND limite = 'MAX'
            AND valor > 0 AND valor <= 8760)
        OR (variable = 'salto_temperatura' AND limite = 'MAX'
            AND valor > 0 AND valor <= 140)
        OR (variable = 'lecturas_congeladas' AND limite = 'MAX'
            AND valor BETWEEN 3 AND 100 AND valor = trunc(valor)))
);

-- Una sola regla activa por variable, límite y severidad.
CREATE UNIQUE INDEX IF NOT EXISTS uq_regla_alerta_activa
    ON regla_alerta (variable, limite, severidad) WHERE activa;

-- Valores iniciales: los umbrales que estaban fijos en el código.
INSERT INTO regla_alerta (variable, limite, valor, severidad, descripcion)
SELECT v.variable, v.limite, v.valor, v.severidad, v.descripcion
FROM (VALUES
    ('temperatura', 'MIN', 2, 'Alta', 'Temperatura baja'),
    ('temperatura', 'MAX', 8, 'Alta', 'Temperatura alta'),
    ('humedad', 'MAX', 80, 'Media', 'Humedad alta'),
    ('vibracion', 'MAX', 15, 'Alta', 'Vibración alta'),
    ('bateria', 'MIN', 20, 'Media', 'Batería baja'),
    ('horas_sin_transmision', 'MAX', 24, 'Media', 'Sensor sin transmisión reciente'),
    ('salto_temperatura', 'MAX', 10, 'Media', 'Salto brusco de temperatura'),
    ('lecturas_congeladas', 'MAX', 6, 'Media', 'Lecturas congeladas')
) AS v(variable, limite, valor, severidad, descripcion)
WHERE NOT EXISTS (SELECT 1 FROM regla_alerta);

-- ------------------------------------------------------------------
-- Quinto reporte cobrable: riesgo de demora de los envíos en curso
-- ------------------------------------------------------------------

INSERT INTO tipo_reporte (codigo, nombre, descripcion, base_datos, precio)
VALUES ('PREDICTIVO', 'Riesgo de demora de mis envíos en curso',
        'Probabilidad de demora, riesgo climático y operativo de cada envío en curso.',
        'MongoDB + PostgreSQL', 15000)
ON CONFLICT (codigo) DO NOTHING;

-- ------------------------------------------------------------------
-- Sensores: estados válidos y motivo de inactividad
-- ------------------------------------------------------------------

ALTER TABLE sensor_iot ADD COLUMN IF NOT EXISTS motivo_inactivo VARCHAR(120);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conname = 'chk_sensor_estado') THEN
        ALTER TABLE sensor_iot ADD CONSTRAINT chk_sensor_estado
            CHECK (estado IN ('Activo', 'Inactivo', 'Mantenimiento'));
    END IF;
END $$;

-- Sensores de envíos ya entregados: pasan a Inactivo para no generar
-- alertas falsas. Solo contenedores sin otro envío en curso.
DO $$
DECLARE
    v_cantidad INTEGER;
BEGIN
    UPDATE sensor_iot s
    SET estado = 'Inactivo',
        motivo_inactivo = 'Entrega del envío ' || ent.id_envio
    FROM (
        SELECT ec.id_contenedor, MAX(e.id_envio) AS id_envio
        FROM envio_contenedor ec
        JOIN envio e ON e.id_envio = ec.id_envio
        WHERE e.estado = 'Entregado'
        GROUP BY ec.id_contenedor
    ) ent
    WHERE s.id_contenedor = ent.id_contenedor
      AND s.estado = 'Activo'
      AND NOT EXISTS (
          SELECT 1 FROM envio_contenedor ec2
          JOIN envio e2 ON e2.id_envio = ec2.id_envio
          WHERE ec2.id_contenedor = s.id_contenedor
            AND e2.estado NOT IN ('Entregado', 'Cancelado'));
    GET DIAGNOSTICS v_cantidad = ROW_COUNT;
    RAISE NOTICE 'Sensores de envíos entregados pasados a Inactivo: %', v_cantidad;
END $$;

-- ------------------------------------------------------------------
-- Sesiones: quién cerró una sesión ajena
-- ------------------------------------------------------------------

ALTER TABLE sesion ADD COLUMN IF NOT EXISTS cerrada_por BIGINT;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conname = 'fk_sesion_cerrada_por') THEN
        ALTER TABLE sesion ADD CONSTRAINT fk_sesion_cerrada_por
            FOREIGN KEY (cerrada_por) REFERENCES usuario(id_usuario);
    END IF;
END $$;

-- ------------------------------------------------------------------
-- Países de los envíos de prueba (aprobados), solo si siguen sin dato
-- ------------------------------------------------------------------

UPDATE envio SET pais_origen = 'Argentina', pais_destino = 'Argentina'
WHERE id_envio = 2 AND origen = 'Buenos Aires' AND destino = 'Cordoba'
  AND pais_origen IS NULL AND pais_destino IS NULL;

UPDATE envio SET pais_origen = 'Argentina', pais_destino = 'España'
WHERE id_envio = 3 AND origen = 'Buenos Aires' AND destino = 'Madrid'
  AND pais_origen IS NULL AND pais_destino IS NULL;

UPDATE envio SET pais_origen = 'Argentina', pais_destino = 'Argentina'
WHERE id_envio = 4 AND origen = 'Buenos Aires' AND destino = 'Rosario'
  AND pais_origen IS NULL AND pais_destino IS NULL;

COMMIT;
