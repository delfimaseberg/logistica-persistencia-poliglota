-- =========================================================
-- LOGÍSTICA POLÍGLOTA
-- Modelo físico Cassandra
-- =========================================================

CREATE KEYSPACE IF NOT EXISTS logistica_poliglota
WITH replication = {
    'class': 'SimpleStrategy',
    'replication_factor': 1
};

USE logistica_poliglota;


-- =========================================================
-- LECTURAS POR SENSOR
-- Historial mensual de lecturas de cada sensor
-- =========================================================

CREATE TABLE IF NOT EXISTS lecturas_por_sensor (
    sensor_id bigint,
    anio_mes text,
    fecha_hora timestamp,
    id_lectura uuid,
    temperatura double,
    humedad double,
    vibracion double,
    gps_latitud double,
    gps_longitud double,
    bateria double,

    PRIMARY KEY (
        (sensor_id, anio_mes),
        fecha_hora,
        id_lectura
    )
)
WITH CLUSTERING ORDER BY (
    fecha_hora DESC,
    id_lectura DESC
);


-- =========================================================
-- LECTURAS POR CONTENEDOR
-- Historial mensual de lecturas de cada contenedor
-- =========================================================

CREATE TABLE IF NOT EXISTS lecturas_por_contenedor (
    contenedor_id bigint,
    anio_mes text,
    fecha_hora timestamp,
    id_lectura uuid,
    sensor_id bigint,
    temperatura double,
    humedad double,
    vibracion double,
    gps_latitud double,
    gps_longitud double,
    bateria double,

    PRIMARY KEY (
        (contenedor_id, anio_mes),
        fecha_hora,
        id_lectura
    )
)
WITH CLUSTERING ORDER BY (
    fecha_hora DESC,
    id_lectura DESC
);


-- =========================================================
-- ÚLTIMA LECTURA POR SENSOR
-- Mantiene el estado más reciente de cada sensor
-- =========================================================

CREATE TABLE IF NOT EXISTS ultima_lectura_por_sensor (
    sensor_id bigint PRIMARY KEY,
    contenedor_id bigint,
    fecha_hora timestamp,
    id_lectura uuid,
    temperatura double,
    humedad double,
    vibracion double,
    gps_latitud double,
    gps_longitud double,
    bateria double
);