-- Estructura para cierres mensuales idempotentes.
-- No determina ni crea saldos iniciales; cada cierre requiere una referencia
-- verificable del saldo inicial antes de poder guardarse.

BEGIN;

CREATE TABLE IF NOT EXISTS cierre_cuenta_corriente (
    id_cierre BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_cliente BIGINT NOT NULL,
    periodo DATE NOT NULL,
    saldo_inicial NUMERIC(14,2) NOT NULL,
    total_facturas NUMERIC(14,2) NOT NULL,
    total_pagos NUMERIC(14,2) NOT NULL,
    saldo_final NUMERIC(14,2) NOT NULL,
    referencia_saldo_inicial TEXT NOT NULL,
    fecha_cierre TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_cierre_cuenta_cliente
        FOREIGN KEY (id_cliente)
        REFERENCES cliente(id_cliente),
    CONSTRAINT uq_cierre_cuenta_cliente_periodo
        UNIQUE (id_cliente, periodo),
    CONSTRAINT chk_cierre_periodo_inicio_mes
        CHECK (EXTRACT(DAY FROM periodo) = 1),
    CONSTRAINT chk_cierre_totales_no_negativos
        CHECK (total_facturas >= 0 AND total_pagos >= 0),
    CONSTRAINT chk_cierre_saldo_consistente
        CHECK (saldo_final = saldo_inicial + total_facturas - total_pagos)
);

COMMIT;
