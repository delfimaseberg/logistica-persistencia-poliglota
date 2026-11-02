-- 016: seguridad de usuarios y sesiones, y controles de datos.
--
-- - Bloqueo por intentos fallidos y cambio obligatorio de contraseña.
-- - Cierre de sesión por inactividad (última actividad de cada sesión).
-- - Email único sin distinguir mayúsculas (usuarios, clientes, proveedores
--   y operadores).
-- - Fechas coherentes en tramos y facturas recibidas.
-- - Corrección del CUIT de Distribuidora del Sur (dígito verificador).
--
-- No modifica contraseñas guardadas, facturas, pagos ni saldos.
-- Idempotente. Requiere 015.

BEGIN;

DO $$
BEGIN
    IF to_regclass('public.regla_alerta') IS NULL THEN
        RAISE EXCEPTION '016 requiere la migración 015';
    END IF;
END $$;

-- ------------------------------------------------------------------
-- Usuarios: bloqueo y cambio obligatorio
-- ------------------------------------------------------------------

ALTER TABLE usuario
    ADD COLUMN IF NOT EXISTS intentos_fallidos SMALLINT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS bloqueado_hasta TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS debe_cambiar_contrasena BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS contrasena_actualizada_en TIMESTAMPTZ;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_usuario_intentos') THEN
        ALTER TABLE usuario ADD CONSTRAINT chk_usuario_intentos
            CHECK (intentos_fallidos >= 0);
    END IF;
END $$;

-- Email único sin distinguir mayúsculas (el inicio de sesión compara en minúsculas).
CREATE UNIQUE INDEX IF NOT EXISTS uq_usuario_email_minusculas ON usuario (lower(email));
CREATE UNIQUE INDEX IF NOT EXISTS uq_cliente_email_minusculas
    ON cliente (lower(email)) WHERE email IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_proveedor_email_minusculas
    ON proveedor (lower(email)) WHERE email IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_operador_email_minusculas
    ON operador_logistico (lower(email)) WHERE email IS NOT NULL;

-- ------------------------------------------------------------------
-- Sesiones: última actividad y estado EXPIRADA (cierre por inactividad)
-- ------------------------------------------------------------------

ALTER TABLE sesion ADD COLUMN IF NOT EXISTS ultima_actividad TIMESTAMPTZ;
UPDATE sesion SET ultima_actividad = fecha_inicio WHERE ultima_actividad IS NULL;
ALTER TABLE sesion
    ALTER COLUMN ultima_actividad SET DEFAULT CURRENT_TIMESTAMP,
    ALTER COLUMN ultima_actividad SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_sesion_estado') THEN
        ALTER TABLE sesion ADD CONSTRAINT chk_sesion_estado
            CHECK (estado IN ('ACTIVA', 'CERRADA', 'EXPIRADA'));
    END IF;
END $$;

-- ------------------------------------------------------------------
-- Fechas coherentes
-- ------------------------------------------------------------------

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_tramo_fechas') THEN
        ALTER TABLE tramo ADD CONSTRAINT chk_tramo_fechas
            CHECK (fecha_salida IS NULL OR fecha_estimada_llegada IS NULL
                   OR fecha_estimada_llegada >= fecha_salida);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_factura_recibida_fechas') THEN
        ALTER TABLE factura_recibida ADD CONSTRAINT chk_factura_recibida_fechas
            CHECK (fecha_vencimiento IS NULL OR fecha_vencimiento >= fecha_emision);
    END IF;
END $$;

-- ------------------------------------------------------------------
-- Datos: CUIT de Distribuidora del Sur con dígito verificador correcto
-- ------------------------------------------------------------------

UPDATE cliente SET cuit = '30-71234567-1'
WHERE cuit = '30-71234567-8' AND razon_social = 'Distribuidora del Sur S.A.';

COMMIT;
