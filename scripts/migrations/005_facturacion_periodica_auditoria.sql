-- Compatibilidad para instalaciones que aplicaron una versiÃ³n anterior de 004.
-- En instalaciones nuevas, 004 ya declara este estado final y esta migraciÃ³n
-- verifica las definiciones sin reemplazar restricciones correctas.
-- Ejecutar despuÃ©s de 004. No crea facturas ni modifica datos de negocio.

BEGIN;

ALTER TABLE factura
    ADD COLUMN IF NOT EXISTS fecha_entrega TIMESTAMPTZ;

ALTER TABLE auditoria_facturacion_periodica
    ADD COLUMN IF NOT EXISTS envio_id_reportado BIGINT;

DO $$
DECLARE
    v_factura_relacion regclass := to_regclass('factura');
    v_auditoria_relacion regclass := to_regclass('auditoria_facturacion_periodica');
    v_esperado text;
    v_actual text;
    v_tipo text;
    v_tipo_restriccion "char";
BEGIN
    IF v_factura_relacion IS NULL OR v_auditoria_relacion IS NULL THEN
        RAISE EXCEPTION
            '005 requiere las tablas factura y auditoria_facturacion_periodica de 004';
    END IF;

    SELECT data_type INTO v_tipo
    FROM information_schema.columns
    WHERE table_schema = current_schema()
      AND table_name = 'factura'
      AND column_name = 'fecha_entrega';
    IF v_tipo IS DISTINCT FROM 'timestamp with time zone' THEN
        RAISE EXCEPTION
            'factura.fecha_entrega debe ser timestamp with time zone; se encontrÃ³ %',
            COALESCE(v_tipo, '<ausente>');
    END IF;

    SELECT data_type INTO v_tipo
    FROM information_schema.columns
    WHERE table_schema = current_schema()
      AND table_name = 'auditoria_facturacion_periodica'
      AND column_name = 'envio_id_reportado';
    IF v_tipo IS DISTINCT FROM 'bigint' THEN
        RAISE EXCEPTION
            'auditoria_facturacion_periodica.envio_id_reportado debe ser bigint; se encontrÃ³ %',
            COALESCE(v_tipo, '<ausente>');
    END IF;

    -- La tabla temporal permite comparar expresiones ya parseadas por esta
    -- versiÃ³n de PostgreSQL. AsÃ­ no se confunden diferencias de formato con
    -- cambios de lÃ³gica en una restricciÃ³n existente.
    CREATE TEMP TABLE _m005_definiciones_esperadas (
        origen_emision VARCHAR(20),
        id_envio BIGINT,
        id_tarifa BIGINT,
        evento_entrega_id TEXT,
        fecha_entrega TIMESTAMPTZ,
        moneda VARCHAR(3),
        importe_base NUMERIC(14,2),
        importe_impuestos NUMERIC(14,2),
        id_configuracion_fiscal BIGINT,
        tratamiento_impositivo TEXT,
        resultado VARCHAR(20),
        envio_id_reportado BIGINT,
        CONSTRAINT chk_factura_automatica_completa CHECK (
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
        ),
        CONSTRAINT chk_auditoria_facturacion_resultado CHECK (
            resultado IN ('BLOQUEADA', 'ERROR', 'FACTURADA')
        ),
        CONSTRAINT chk_auditoria_facturacion_envio_referido CHECK (
            id_envio IS NOT NULL OR envio_id_reportado IS NOT NULL
        )
    ) ON COMMIT DROP;

    -- Permitir auditar intentos bloqueados aunque no haya un id_envio local.
    SELECT is_nullable INTO v_tipo
    FROM information_schema.columns
    WHERE table_schema = current_schema()
      AND table_name = 'auditoria_facturacion_periodica'
      AND column_name = 'id_envio';
    IF v_tipo IS NULL THEN
        RAISE EXCEPTION 'Falta auditoria_facturacion_periodica.id_envio';
    ELSIF v_tipo <> 'YES' THEN
        ALTER TABLE auditoria_facturacion_periodica
            ALTER COLUMN id_envio DROP NOT NULL;
    END IF;

    -- Si existe una restricciÃ³n con el nombre esperado, solo se conserva si
    -- expresa exactamente la misma regla que la definiciÃ³n canÃ³nica.
    SELECT pg_get_expr(conbin, conrelid) INTO v_esperado
    FROM pg_constraint
    WHERE conrelid = 'pg_temp._m005_definiciones_esperadas'::regclass
      AND conname = 'chk_factura_automatica_completa';
    SELECT contype, pg_get_expr(conbin, conrelid)
    INTO v_tipo_restriccion, v_actual
    FROM pg_constraint
    WHERE conrelid = v_factura_relacion
      AND conname = 'chk_factura_automatica_completa';
    IF v_tipo_restriccion IS NULL THEN
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
    ELSIF v_tipo_restriccion <> 'c' OR v_actual IS DISTINCT FROM v_esperado THEN
        RAISE EXCEPTION
            'chk_factura_automatica_completa existe con una definiciÃ³n inesperada; revisar antes de continuar';
    END IF;

    SELECT pg_get_expr(conbin, conrelid) INTO v_esperado
    FROM pg_constraint
    WHERE conrelid = 'pg_temp._m005_definiciones_esperadas'::regclass
      AND conname = 'chk_auditoria_facturacion_resultado';
    SELECT contype, pg_get_expr(conbin, conrelid)
    INTO v_tipo_restriccion, v_actual
    FROM pg_constraint
    WHERE conrelid = v_auditoria_relacion
      AND conname = 'chk_auditoria_facturacion_resultado';
    IF v_tipo_restriccion IS NULL THEN
        ALTER TABLE auditoria_facturacion_periodica
            ADD CONSTRAINT chk_auditoria_facturacion_resultado
            CHECK (resultado IN ('BLOQUEADA', 'ERROR', 'FACTURADA'));
    ELSIF v_tipo_restriccion <> 'c' OR v_actual IS DISTINCT FROM v_esperado THEN
        RAISE EXCEPTION
            'chk_auditoria_facturacion_resultado existe con una definiciÃ³n inesperada; revisar antes de continuar';
    END IF;

    SELECT pg_get_expr(conbin, conrelid) INTO v_esperado
    FROM pg_constraint
    WHERE conrelid = 'pg_temp._m005_definiciones_esperadas'::regclass
      AND conname = 'chk_auditoria_facturacion_envio_referido';
    SELECT contype, pg_get_expr(conbin, conrelid)
    INTO v_tipo_restriccion, v_actual
    FROM pg_constraint
    WHERE conrelid = v_auditoria_relacion
      AND conname = 'chk_auditoria_facturacion_envio_referido';
    IF v_tipo_restriccion IS NULL THEN
        ALTER TABLE auditoria_facturacion_periodica
            ADD CONSTRAINT chk_auditoria_facturacion_envio_referido
            CHECK (id_envio IS NOT NULL OR envio_id_reportado IS NOT NULL);
    ELSIF v_tipo_restriccion <> 'c' OR v_actual IS DISTINCT FROM v_esperado THEN
        RAISE EXCEPTION
            'chk_auditoria_facturacion_envio_referido existe con una definiciÃ³n inesperada; revisar antes de continuar';
    END IF;
END $$;

COMMIT;
