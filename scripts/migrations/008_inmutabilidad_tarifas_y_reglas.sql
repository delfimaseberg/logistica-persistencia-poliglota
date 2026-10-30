-- Protege snapshots aprobados y conserva reglas tarifarias versionadas.
-- Requiere 004 y 007. No modifica importes ni datos de negocio.
-- El reemplazo autorizado se registra y cambia de estado en una transacción.

BEGIN;

DO $$
BEGIN
    IF to_regclass('public.tarifa_envio') IS NULL
       OR to_regclass('public.tarifa_envio_auditoria') IS NULL
       OR to_regclass('public.factura') IS NULL
       OR to_regclass('public.regla_tarifaria_version') IS NULL
       OR to_regclass('public.regla_tarifaria_componente') IS NULL
       OR to_regclass('public.regla_tarifaria_auditoria') IS NULL THEN
        RAISE EXCEPTION '008 requiere las migraciones 004 y 007';
    END IF;
END $$;

ALTER TABLE tarifa_envio_auditoria
    ADD COLUMN IF NOT EXISTS id_transaccion BIGINT;

ALTER TABLE regla_tarifaria_auditoria
    ADD COLUMN IF NOT EXISTS id_transaccion BIGINT;

CREATE OR REPLACE FUNCTION proteger_tarifa_envio_inmutable()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.estado <> 'BORRADOR' THEN
            RAISE EXCEPTION 'Una tarifa debe crearse como BORRADOR y aprobarse con auditoría.';
        END IF;
        RETURN NEW;
    END IF;

    IF TG_OP = 'DELETE' THEN
        IF OLD.estado <> 'BORRADOR'
           OR EXISTS (SELECT 1 FROM tarifa_envio_auditoria a
                      WHERE a.id_tarifa = OLD.id_tarifa)
           OR EXISTS (SELECT 1 FROM factura f
                      WHERE f.id_tarifa = OLD.id_tarifa) THEN
            RAISE EXCEPTION
                'No se puede borrar una tarifa conservada por su estado, auditoría o factura.';
        END IF;
        RETURN OLD;
    END IF;

    IF OLD.estado = 'APROBADA' THEN
        IF NEW.estado <> 'REEMPLAZADA' THEN
            RAISE EXCEPTION
                'Una tarifa aprobada es inmutable; solo puede pasar a REEMPLAZADA con auditoría.';
        END IF;

        IF (to_jsonb(NEW) - 'estado') IS DISTINCT FROM (to_jsonb(OLD) - 'estado') THEN
            RAISE EXCEPTION
                'El contenido de una tarifa aprobada no puede modificarse al reemplazarla.';
        END IF;

        IF EXISTS (SELECT 1 FROM factura f WHERE f.id_tarifa = OLD.id_tarifa) THEN
            RAISE EXCEPTION
                'No se puede reemplazar una tarifa referenciada por una factura.';
        END IF;

        IF NOT EXISTS (
            SELECT 1 FROM tarifa_envio_auditoria a
            WHERE a.id_tarifa = OLD.id_tarifa
              AND a.estado_anterior = 'APROBADA'
              AND a.estado_nuevo = 'REEMPLAZADA'
              AND a.id_transaccion = txid_current()
              AND length(trim(a.motivo)) > 0
        ) THEN
            RAISE EXCEPTION
                'El reemplazo requiere una auditoría con motivo en la misma transacción.';
        END IF;
        RETURN NEW;
    END IF;

    IF OLD.estado = 'REEMPLAZADA' THEN
        RAISE EXCEPTION 'Una tarifa reemplazada es histórica e inmutable.';
    END IF;

    IF OLD.estado = 'BORRADOR' THEN
        IF NEW.estado NOT IN ('BORRADOR', 'APROBADA') THEN
            RAISE EXCEPTION 'Transición de estado de borrador no autorizada.';
        END IF;
        IF NEW.estado = 'APROBADA' AND NOT EXISTS (
            SELECT 1 FROM tarifa_envio_auditoria a
            WHERE a.id_tarifa = OLD.id_tarifa
              AND a.estado_anterior = 'BORRADOR'
              AND a.estado_nuevo = 'APROBADA'
              AND a.id_transaccion = txid_current()
              AND length(trim(a.motivo)) > 0
        ) THEN
            RAISE EXCEPTION
                'La aprobación requiere una auditoría con motivo en la misma transacción.';
        END IF;
        RETURN NEW;
    END IF;

    RAISE EXCEPTION 'Estado de tarifa no reconocido; operación bloqueada.';
END;
$$;

CREATE OR REPLACE FUNCTION proteger_regla_tarifaria_historial()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.estado <> 'BORRADOR' THEN
            RAISE EXCEPTION 'Una versión de regla debe crearse como BORRADOR.';
        END IF;
        RETURN NEW;
    END IF;

    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION
            'Las versiones de reglas se conservan para auditoría; no se pueden borrar.';
    END IF;

    IF OLD.estado = 'BORRADOR' THEN
        IF NEW.estado NOT IN ('BORRADOR', 'APROBADA') THEN
            RAISE EXCEPTION 'Transición de estado de regla borrador no autorizada.';
        END IF;
        IF NEW.estado = 'APROBADA' AND NOT EXISTS (
            SELECT 1 FROM regla_tarifaria_auditoria a
            WHERE a.id_regla = OLD.id_regla
              AND a.estado_anterior = 'BORRADOR'
              AND a.estado_nuevo = 'APROBADA'
              AND a.id_transaccion = txid_current()
              AND length(trim(a.motivo)) > 0
        ) THEN
            RAISE EXCEPTION
                'La aprobación de regla requiere auditoría con motivo en la misma transacción.';
        END IF;
        RETURN NEW;
    END IF;

    IF OLD.estado = 'APROBADA' THEN
        IF NEW.estado <> 'REEMPLAZADA' THEN
            RAISE EXCEPTION
                'Una regla aprobada es inmutable; solo puede reemplazarse con auditoría.';
        END IF;
        IF (to_jsonb(NEW) - 'estado') IS DISTINCT FROM (to_jsonb(OLD) - 'estado') THEN
            RAISE EXCEPTION 'El contenido de una regla aprobada no puede modificarse.';
        END IF;
        IF NOT EXISTS (
            SELECT 1 FROM regla_tarifaria_auditoria a
            WHERE a.id_regla = OLD.id_regla
              AND a.estado_anterior = 'APROBADA'
              AND a.estado_nuevo = 'REEMPLAZADA'
              AND a.id_transaccion = txid_current()
              AND length(trim(a.motivo)) > 0
        ) THEN
            RAISE EXCEPTION
                'El reemplazo de regla requiere auditoría con motivo en la misma transacción.';
        END IF;
        RETURN NEW;
    END IF;

    RAISE EXCEPTION 'Una regla reemplazada es histórica e inmutable.';
END;
$$;

CREATE OR REPLACE FUNCTION proteger_componentes_regla_tarifaria()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_id_regla BIGINT;
BEGIN
    IF TG_OP = 'DELETE' THEN
        v_id_regla := OLD.id_regla;
    ELSE
        v_id_regla := NEW.id_regla;
    END IF;

    IF TG_OP = 'UPDATE' AND OLD.id_regla IS DISTINCT FROM NEW.id_regla THEN
        IF EXISTS (
            SELECT 1 FROM regla_tarifaria_version r
            WHERE r.id_regla = OLD.id_regla AND r.estado <> 'BORRADOR'
        ) THEN
            RAISE EXCEPTION
                'No se pueden mover componentes fuera de reglas aprobadas o reemplazadas.';
        END IF;
    END IF;

    IF EXISTS (
        SELECT 1 FROM regla_tarifaria_version r
        WHERE r.id_regla = v_id_regla AND r.estado <> 'BORRADOR'
    ) THEN
        RAISE EXCEPTION
            'Los componentes de reglas aprobadas o reemplazadas son inmutables.';
    END IF;

    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_tarifa_envio_inmutable ON tarifa_envio;
CREATE TRIGGER trg_tarifa_envio_inmutable
    BEFORE INSERT OR UPDATE OR DELETE ON tarifa_envio
    FOR EACH ROW EXECUTE FUNCTION proteger_tarifa_envio_inmutable();

DROP TRIGGER IF EXISTS trg_regla_tarifaria_inmutable
    ON regla_tarifaria_version;
CREATE TRIGGER trg_regla_tarifaria_inmutable
    BEFORE INSERT OR UPDATE OR DELETE ON regla_tarifaria_version
    FOR EACH ROW EXECUTE FUNCTION proteger_regla_tarifaria_historial();

DROP TRIGGER IF EXISTS trg_regla_tarifaria_componente_inmutable
    ON regla_tarifaria_componente;
CREATE TRIGGER trg_regla_tarifaria_componente_inmutable
    BEFORE INSERT OR UPDATE OR DELETE ON regla_tarifaria_componente
    FOR EACH ROW EXECUTE FUNCTION proteger_componentes_regla_tarifaria();

COMMIT;
