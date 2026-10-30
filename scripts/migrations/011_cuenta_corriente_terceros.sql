-- 011: cuenta corriente de proveedores y operadores logísticos.
--
-- Tablas paralelas a las del cliente (no se modifican cuenta_corriente,
-- factura, pago ni movimiento_cuenta_corriente). El saldo es lo que NOSOTROS
-- les debemos: una factura recibida lo aumenta y un pago nuestro lo reduce.
-- Aditiva e idempotente; no inserta datos.

BEGIN;

CREATE TABLE IF NOT EXISTS cuenta_corriente_tercero (
    id_cuenta_tercero BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_proveedor BIGINT REFERENCES proveedor(id_proveedor),
    id_operador BIGINT REFERENCES operador_logistico(id_operador),
    saldo NUMERIC(14,2) NOT NULL DEFAULT 0,
    moneda VARCHAR(3) NOT NULL DEFAULT 'ARS',
    fecha_actualizacion TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_cct_un_titular
        CHECK (num_nonnulls(id_proveedor, id_operador) = 1),
    CONSTRAINT chk_cct_moneda CHECK (moneda = 'ARS'),
    -- No se admiten pagos mayores a lo pendiente, así que nunca hay saldo
    -- a favor nuestro.
    CONSTRAINT chk_cct_saldo_no_negativo CHECK (saldo >= 0)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_cct_proveedor
    ON cuenta_corriente_tercero (id_proveedor) WHERE id_proveedor IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_cct_operador
    ON cuenta_corriente_tercero (id_operador) WHERE id_operador IS NOT NULL;

CREATE TABLE IF NOT EXISTS factura_recibida (
    id_factura_recibida BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_proveedor BIGINT REFERENCES proveedor(id_proveedor),
    id_operador BIGINT REFERENCES operador_logistico(id_operador),
    numero_comprobante VARCHAR(30) NOT NULL,
    fecha_emision DATE NOT NULL,
    fecha_vencimiento DATE NOT NULL,
    total NUMERIC(14,2) NOT NULL,
    moneda VARCHAR(3) NOT NULL DEFAULT 'ARS',
    estado VARCHAR(10) NOT NULL DEFAULT 'Pendiente',
    id_tramo BIGINT REFERENCES tramo(id_tramo),
    concepto VARCHAR(255),
    registrado_por BIGINT REFERENCES usuario(id_usuario),
    registrado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_fr_un_titular
        CHECK (num_nonnulls(id_proveedor, id_operador) = 1),
    CONSTRAINT chk_fr_total CHECK (total > 0),
    CONSTRAINT chk_fr_moneda CHECK (moneda = 'ARS'),
    CONSTRAINT chk_fr_estado
        CHECK (estado IN ('Pendiente', 'Parcial', 'Pagada', 'Anulada')),
    CONSTRAINT chk_fr_vencimiento CHECK (fecha_vencimiento >= fecha_emision),
    CONSTRAINT chk_fr_comprobante CHECK (btrim(numero_comprobante) <> ''),
    -- Operador: siempre ligada al tramo que realizó.
    -- Proveedor: sin tramo y con concepto.
    CONSTRAINT chk_fr_origen CHECK (
        (id_operador IS NOT NULL AND id_tramo IS NOT NULL)
        OR (
            id_proveedor IS NOT NULL
            AND id_tramo IS NULL
            AND concepto IS NOT NULL
            AND btrim(concepto) <> ''
        )
    )
);

-- La misma factura del emisor no se carga dos veces.
CREATE UNIQUE INDEX IF NOT EXISTS uq_fr_comprobante_proveedor
    ON factura_recibida (id_proveedor, upper(numero_comprobante))
    WHERE id_proveedor IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_fr_comprobante_operador
    ON factura_recibida (id_operador, upper(numero_comprobante))
    WHERE id_operador IS NOT NULL;
-- Una factura por tramo, salvo anuladas.
CREATE UNIQUE INDEX IF NOT EXISTS uq_fr_tramo_vigente
    ON factura_recibida (id_tramo)
    WHERE id_tramo IS NOT NULL AND estado <> 'Anulada';
CREATE INDEX IF NOT EXISTS idx_fr_vencimiento_pendientes
    ON factura_recibida (fecha_vencimiento)
    WHERE estado IN ('Pendiente', 'Parcial');

CREATE TABLE IF NOT EXISTS pago_emitido (
    id_pago_emitido BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_factura_recibida BIGINT NOT NULL
        REFERENCES factura_recibida(id_factura_recibida),
    fecha TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    monto NUMERIC(14,2) NOT NULL,
    metodo_pago VARCHAR(30) NOT NULL,
    referencia VARCHAR(100),
    registrado_por BIGINT REFERENCES usuario(id_usuario),
    CONSTRAINT chk_pe_monto CHECK (monto > 0)
);

CREATE INDEX IF NOT EXISTS idx_pe_factura ON pago_emitido (id_factura_recibida);

CREATE TABLE IF NOT EXISTS movimiento_cuenta_tercero (
    id_movimiento BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_cuenta_tercero BIGINT NOT NULL
        REFERENCES cuenta_corriente_tercero(id_cuenta_tercero),
    moneda VARCHAR(3) NOT NULL,
    tipo_movimiento VARCHAR(30) NOT NULL,
    importe_firmado NUMERIC(14,2) NOT NULL,
    fecha_contable DATE NOT NULL,
    tipo_origen VARCHAR(40) NOT NULL,
    referencia_origen TEXT NOT NULL,
    referencia_documental TEXT,
    registrado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_mct_origen
        UNIQUE (tipo_origen, referencia_origen, tipo_movimiento),
    CONSTRAINT chk_mct_tipo
        CHECK (tipo_movimiento IN ('FACTURA_RECIBIDA', 'PAGO_EMITIDO')),
    -- Factura recibida: aumenta lo que debemos. Pago nuestro: lo reduce.
    CONSTRAINT chk_mct_signo CHECK (
        (tipo_movimiento = 'FACTURA_RECIBIDA' AND importe_firmado > 0)
        OR (tipo_movimiento = 'PAGO_EMITIDO' AND importe_firmado < 0)
    )
);

CREATE INDEX IF NOT EXISTS idx_mct_cuenta_fecha
    ON movimiento_cuenta_tercero (id_cuenta_tercero, fecha_contable);

COMMIT;
