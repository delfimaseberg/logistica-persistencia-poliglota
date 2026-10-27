-- Extiende el borrador 002 sin eliminar cierres ni movimientos existentes.
-- Debe revisarse y ejecutarse solo después de verificar la secuencia de
-- migraciones del entorno destino. No inicializa monedas ni saldos.

BEGIN;

ALTER TABLE cuenta_corriente
    ADD COLUMN IF NOT EXISTS moneda VARCHAR(3);

CREATE TABLE IF NOT EXISTS apertura_cuenta_corriente (
    id_apertura BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_cliente BIGINT NOT NULL UNIQUE,
    moneda VARCHAR(3) NOT NULL,
    saldo_inicial NUMERIC(14,2) NOT NULL,
    fecha_vigencia DATE NOT NULL,
    referencia_fuente TEXT NOT NULL,
    aprobado_por BIGINT NOT NULL,
    aprobado_en TIMESTAMPTZ NOT NULL,
    creado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_apertura_cliente
        FOREIGN KEY (id_cliente) REFERENCES cliente(id_cliente),
    CONSTRAINT fk_apertura_aprobador
        FOREIGN KEY (aprobado_por) REFERENCES usuario(id_usuario)
);

CREATE TABLE IF NOT EXISTS movimiento_cuenta_corriente (
    id_movimiento BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_cliente BIGINT NOT NULL,
    moneda VARCHAR(3) NOT NULL,
    tipo_movimiento VARCHAR(30) NOT NULL,
    importe_firmado NUMERIC(14,2) NOT NULL,
    fecha_contable DATE NOT NULL,
    periodo_origen DATE,
    tipo_origen VARCHAR(40) NOT NULL,
    referencia_origen TEXT NOT NULL,
    referencia_documental TEXT,
    registrado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_movimiento_cliente
        FOREIGN KEY (id_cliente) REFERENCES cliente(id_cliente),
    CONSTRAINT uq_movimiento_origen
        UNIQUE (tipo_origen, referencia_origen, tipo_movimiento),
    CONSTRAINT chk_movimiento_importe_no_cero
        CHECK (importe_firmado <> 0),
    CONSTRAINT chk_movimiento_periodo_origen
        CHECK (periodo_origen IS NULL OR EXTRACT(DAY FROM periodo_origen) = 1)
);

CREATE INDEX IF NOT EXISTS idx_movimiento_cliente_fecha
    ON movimiento_cuenta_corriente (id_cliente, fecha_contable);

CREATE TABLE IF NOT EXISTS cierre_cuenta_corriente (
    id_cierre BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_cliente BIGINT NOT NULL,
    periodo DATE NOT NULL,
    moneda VARCHAR(3) NOT NULL,
    saldo_inicial NUMERIC(14,2) NOT NULL,
    total_facturas NUMERIC(14,2) NOT NULL,
    total_pagos NUMERIC(14,2) NOT NULL,
    ajustes_netos NUMERIC(14,2) NOT NULL,
    saldo_final NUMERIC(14,2) NOT NULL,
    referencia_saldo_inicial TEXT NOT NULL,
    id_apertura BIGINT,
    fecha_cierre TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_cierre_cuenta_cliente
        FOREIGN KEY (id_cliente) REFERENCES cliente(id_cliente),
    CONSTRAINT fk_cierre_apertura
        FOREIGN KEY (id_apertura) REFERENCES apertura_cuenta_corriente(id_apertura),
    CONSTRAINT uq_cierre_cuenta_cliente_periodo UNIQUE (id_cliente, periodo),
    CONSTRAINT chk_cierre_periodo_inicio_mes
        CHECK (EXTRACT(DAY FROM periodo) = 1),
    CONSTRAINT chk_cierre_totales_no_negativos
        CHECK (total_facturas >= 0 AND total_pagos >= 0),
    CONSTRAINT chk_cierre_importes_consistentes
        CHECK (
            saldo_final = saldo_inicial + total_facturas
                          - total_pagos + ajustes_netos
        )
);

-- La migración 002 puede haberse aplicado en algún entorno. Se conservan sus
-- filas y se amplía el esquema de forma compatible en ambos casos.
ALTER TABLE cierre_cuenta_corriente
    ADD COLUMN IF NOT EXISTS moneda VARCHAR(3),
    ADD COLUMN IF NOT EXISTS ajustes_netos NUMERIC(14,2),
    ADD COLUMN IF NOT EXISTS id_apertura BIGINT;

ALTER TABLE cierre_cuenta_corriente
    DROP CONSTRAINT IF EXISTS chk_cierre_saldo_consistente;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_cierre_apertura'
          AND conrelid = 'cierre_cuenta_corriente'::regclass
    ) THEN
        ALTER TABLE cierre_cuenta_corriente
            ADD CONSTRAINT fk_cierre_apertura
            FOREIGN KEY (id_apertura)
            REFERENCES apertura_cuenta_corriente(id_apertura);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_cierre_financiero_completo'
          AND conrelid = 'cierre_cuenta_corriente'::regclass
    ) THEN
        ALTER TABLE cierre_cuenta_corriente
            ADD CONSTRAINT chk_cierre_financiero_completo
            CHECK (
                moneda IS NOT NULL
                AND ajustes_netos IS NOT NULL
                AND saldo_final = saldo_inicial + total_facturas
                                  - total_pagos + ajustes_netos
            ) NOT VALID;
    END IF;
END $$;

COMMIT;
