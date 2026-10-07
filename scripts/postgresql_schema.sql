-- =========================================================
-- LOGÍSTICA POLÍGLOTA
-- Modelo físico PostgreSQL
-- =========================================================


-- =========================
-- CLIENTE
-- =========================
CREATE TABLE cliente (
    id_cliente BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    razon_social VARCHAR(150) NOT NULL,
    cuit VARCHAR(13) NOT NULL UNIQUE,
    email VARCHAR(150) NOT NULL,
    telefono VARCHAR(30),
    direccion VARCHAR(255),
    pais VARCHAR(80) NOT NULL,
    estado VARCHAR(20) NOT NULL
);


-- =========================
-- ROL
-- =========================
CREATE TABLE rol (
    id_rol SMALLINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    descripcion VARCHAR(255) NOT NULL,
    nivel_permisos SMALLINT NOT NULL,
    
    CONSTRAINT chk_rol_nivel_permisos CHECK (nivel_permisos BETWEEN 0 AND 5)
);


-- =========================
-- USUARIO
-- =========================
CREATE TABLE usuario (
    id_usuario BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_cliente BIGINT NOT NULL,
    id_rol SMALLINT NOT NULL,
    nombre VARCHAR(80) NOT NULL,
    apellido VARCHAR(80) NOT NULL,
    email VARCHAR(150) NOT NULL UNIQUE,
    contrasena_encriptada VARCHAR(255) NOT NULL,
    estado VARCHAR(20) NOT NULL,
    fecha_registro TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_usuario_cliente
        FOREIGN KEY (id_cliente)
        REFERENCES cliente(id_cliente),

    CONSTRAINT fk_usuario_rol
        FOREIGN KEY (id_rol)
        REFERENCES rol(id_rol)
);


-- =========================
-- SESION
-- =========================
CREATE TABLE sesion (
    id_sesion BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_usuario BIGINT NOT NULL,
    fecha_inicio TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fecha_fin TIMESTAMPTZ,
    estado VARCHAR(20) NOT NULL,

    CONSTRAINT fk_sesion_usuario
        FOREIGN KEY (id_usuario)
        REFERENCES usuario(id_usuario),

    CONSTRAINT chk_sesion_fechas
        CHECK (
            fecha_fin IS NULL
            OR fecha_fin >= fecha_inicio
        )
);


-- =========================
-- CONTENEDOR
-- =========================
CREATE TABLE contenedor (
    id_contenedor BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    codigo_internacional VARCHAR(20) NOT NULL UNIQUE,
    tipo VARCHAR(30) NOT NULL,
    capacidad NUMERIC(10,2) NOT NULL,
    estado VARCHAR(20) NOT NULL,

    CONSTRAINT chk_contenedor_capacidad
        CHECK (capacidad > 0)
);


-- =========================
-- SENSOR IoT
-- =========================
CREATE TABLE sensor_iot (
    id_sensor BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_contenedor BIGINT NOT NULL,
    tipo VARCHAR(30) NOT NULL,
    fabricante VARCHAR(100),
    fecha_instalacion DATE,
    estado VARCHAR(20) NOT NULL,

    CONSTRAINT fk_sensor_contenedor
        FOREIGN KEY (id_contenedor)
        REFERENCES contenedor(id_contenedor)
);


-- =========================
-- ENVIO
-- =========================
CREATE TABLE envio (
    id_envio BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_cliente BIGINT NOT NULL,
    fecha_creacion TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    origen VARCHAR(150) NOT NULL,
    destino VARCHAR(150) NOT NULL,
    estado VARCHAR(20) NOT NULL,
    prioridad VARCHAR(20) NOT NULL,

    CONSTRAINT fk_envio_cliente
        FOREIGN KEY (id_cliente)
        REFERENCES cliente(id_cliente)
);


-- =========================
-- ENVIO - CONTENEDOR
-- Relación N:M
-- =========================
CREATE TABLE envio_contenedor (
    id_envio BIGINT NOT NULL,
    id_contenedor BIGINT NOT NULL,

    PRIMARY KEY (id_envio, id_contenedor),

    CONSTRAINT fk_envio_contenedor_envio
        FOREIGN KEY (id_envio)
        REFERENCES envio(id_envio),

    CONSTRAINT fk_envio_contenedor_contenedor
        FOREIGN KEY (id_contenedor)
        REFERENCES contenedor(id_contenedor)
);


-- =========================
-- VEHICULO
-- =========================
CREATE TABLE vehiculo (
    id_vehiculo BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tipo VARCHAR(30) NOT NULL,
    identificacion VARCHAR(50) NOT NULL UNIQUE,
    empresa_operadora VARCHAR(100),
    estado VARCHAR(20) NOT NULL
);


-- =========================
-- TRAMO
-- =========================
CREATE TABLE tramo (
    id_tramo BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_envio BIGINT NOT NULL,
    id_vehiculo BIGINT NOT NULL,
    medio_transporte VARCHAR(20) NOT NULL,
    origen VARCHAR(150) NOT NULL,
    destino VARCHAR(150) NOT NULL,
    fecha_salida TIMESTAMPTZ NOT NULL,
    fecha_estimada_llegada TIMESTAMPTZ NOT NULL,

    CONSTRAINT fk_tramo_envio
        FOREIGN KEY (id_envio)
        REFERENCES envio(id_envio),

    CONSTRAINT fk_tramo_vehiculo
        FOREIGN KEY (id_vehiculo)
        REFERENCES vehiculo(id_vehiculo),

    CONSTRAINT chk_tramo_fechas
        CHECK (fecha_estimada_llegada >= fecha_salida)
);


-- =========================
-- INCIDENTE
-- =========================
CREATE TABLE incidente (
    id_incidente BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_envio BIGINT NOT NULL,
    tipo VARCHAR(50) NOT NULL,
    fecha TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    severidad VARCHAR(20) NOT NULL,
    estado VARCHAR(20) NOT NULL,
    descripcion TEXT,

    CONSTRAINT fk_incidente_envio
        FOREIGN KEY (id_envio)
        REFERENCES envio(id_envio)
);


-- =========================
-- REPORTE
-- =========================
CREATE TABLE reporte (
    id_reporte BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_usuario BIGINT NOT NULL,
    tipo VARCHAR(50) NOT NULL,
    fecha_generacion TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    formato VARCHAR(10) NOT NULL,
    estado VARCHAR(20) NOT NULL,

    CONSTRAINT fk_reporte_usuario
        FOREIGN KEY (id_usuario)
        REFERENCES usuario(id_usuario),

    CONSTRAINT chk_reporte_formato
        CHECK (formato IN ('PDF', 'CSV'))
);


-- =========================
-- FACTURA
-- =========================
CREATE TABLE factura (
    id_factura BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_cliente BIGINT NOT NULL,
    fecha_emision DATE NOT NULL,
    total NUMERIC(14,2) NOT NULL,
    estado VARCHAR(20) NOT NULL,

    CONSTRAINT fk_factura_cliente
        FOREIGN KEY (id_cliente)
        REFERENCES cliente(id_cliente),

    CONSTRAINT chk_factura_total
        CHECK (total >= 0)
);


-- =========================
-- PAGO
-- =========================
CREATE TABLE pago (
    id_pago BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_factura BIGINT NOT NULL,
    fecha TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    monto NUMERIC(14,2) NOT NULL,
    metodo_pago VARCHAR(30) NOT NULL,

    CONSTRAINT fk_pago_factura
        FOREIGN KEY (id_factura)
        REFERENCES factura(id_factura),

    CONSTRAINT chk_pago_monto
        CHECK (monto > 0)
);


-- =========================
-- CUENTA CORRIENTE
-- =========================
CREATE TABLE cuenta_corriente (
    id_cuenta BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_cliente BIGINT NOT NULL UNIQUE,
    saldo NUMERIC(14,2) NOT NULL DEFAULT 0,
    fecha_actualizacion TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_cuenta_cliente
        FOREIGN KEY (id_cliente)
        REFERENCES cliente(id_cliente)
);


-- =========================================================
-- ÍNDICES
-- =========================================================

CREATE INDEX idx_usuario_cliente
    ON usuario(id_cliente);

CREATE INDEX idx_envio_cliente
    ON envio(id_cliente);

CREATE INDEX idx_sensor_contenedor
    ON sensor_iot(id_contenedor);

CREATE INDEX idx_tramo_envio
    ON tramo(id_envio);

CREATE INDEX idx_tramo_vehiculo
    ON tramo(id_vehiculo);

CREATE INDEX idx_incidente_envio
    ON incidente(id_envio);

CREATE INDEX idx_factura_cliente
    ON factura(id_cliente);

CREATE INDEX idx_pago_factura
    ON pago(id_factura);