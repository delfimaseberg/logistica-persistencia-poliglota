-- 009 - Configura explícitamente la moneda ARS en registros existentes.
--
-- Requiere 003 (cuenta_corriente.moneda) y 004 (factura.moneda).
--
-- Decisión del grupo: el sistema opera con una única moneda, pesos
-- argentinos (ARS). Las migraciones 003/004 agregaron las columnas de moneda
-- vacías a propósito; este script deja registrada esa decisión.
--
-- Qué hace:
--   * Completa moneda = 'ARS' SOLO donde hoy es NULL (no pisa valores).
--   * Agrega un CHECK para que la moneda sea un código de 3 letras mayúsculas.
--
-- Qué NO hace (a propósito):
--   * No crea movimientos históricos en movimiento_cuenta_corriente.
--   * No crea aperturas, saldos iniciales, fechas ni aprobaciones.
--   * No modifica saldos, importes, estados ni fechas.
--
-- Es idempotente: ejecutarlo dos veces no cambia nada la segunda vez.

BEGIN;

DO $$
DECLARE
    v_cuentas integer;
    v_facturas integer;
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = 'cuenta_corriente' AND column_name = 'moneda'
    ) THEN
        RAISE EXCEPTION '009 requiere la migración 003 (cuenta_corriente.moneda)';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = 'factura' AND column_name = 'moneda'
    ) THEN
        RAISE EXCEPTION '009 requiere la migración 004 (factura.moneda)';
    END IF;

    -- Si ya hubiera otra moneda cargada, no se asume ARS para el resto.
    IF EXISTS (SELECT 1 FROM cuenta_corriente WHERE moneda IS NOT NULL AND moneda <> 'ARS')
       OR EXISTS (SELECT 1 FROM factura WHERE moneda IS NOT NULL AND moneda <> 'ARS') THEN
        RAISE EXCEPTION 'Hay registros con moneda distinta de ARS; revisar antes de continuar';
    END IF;

    UPDATE cuenta_corriente SET moneda = 'ARS' WHERE moneda IS NULL;
    GET DIAGNOSTICS v_cuentas = ROW_COUNT;

    UPDATE factura SET moneda = 'ARS' WHERE moneda IS NULL;
    GET DIAGNOSTICS v_facturas = ROW_COUNT;

    RAISE NOTICE '009: cuentas actualizadas = %, facturas actualizadas = %',
        v_cuentas, v_facturas;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_cuenta_corriente_moneda'
          AND conrelid = 'cuenta_corriente'::regclass
    ) THEN
        ALTER TABLE cuenta_corriente ADD CONSTRAINT chk_cuenta_corriente_moneda
            CHECK (moneda IS NULL OR moneda ~ '^[A-Z]{3}$');
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_factura_moneda'
          AND conrelid = 'factura'::regclass
    ) THEN
        ALTER TABLE factura ADD CONSTRAINT chk_factura_moneda
            CHECK (moneda IS NULL OR moneda ~ '^[A-Z]{3}$');
    END IF;
END $$;

COMMIT;
