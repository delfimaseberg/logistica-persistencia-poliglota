-- Refuerza la inmutabilidad de snapshots de cierre ya creados.
-- Ejecutar después de crear cierre_cuenta_corriente (migraciones 002/003).
BEGIN;

CREATE OR REPLACE FUNCTION rechazar_cambio_cierre_cuenta_corriente()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION
        'Los cierres de cuenta corriente son snapshots inmutables; registre una corrección auditada.'
        USING ERRCODE = '55000';
END;
$$;

DROP TRIGGER IF EXISTS trg_cierre_cuenta_inmutable
    ON cierre_cuenta_corriente;

CREATE TRIGGER trg_cierre_cuenta_inmutable
    BEFORE UPDATE OR DELETE ON cierre_cuenta_corriente
    FOR EACH ROW
    EXECUTE FUNCTION rechazar_cambio_cierre_cuenta_corriente();

DROP TRIGGER IF EXISTS trg_cierre_cuenta_inmutable_truncate
    ON cierre_cuenta_corriente;

CREATE TRIGGER trg_cierre_cuenta_inmutable_truncate
    BEFORE TRUNCATE ON cierre_cuenta_corriente
    FOR EACH STATEMENT
    EXECUTE FUNCTION rechazar_cambio_cierre_cuenta_corriente();

COMMIT;
