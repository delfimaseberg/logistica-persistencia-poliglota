
from datetime import datetime, timezone
from uuid import uuid4

from cassandra.query import BatchStatement, BatchType

from app.database.cassandra_connection import get_cassandra_session


KEYSPACE = "logistica_poliglota"


def abrir_conexion():
    cluster, session = get_cassandra_session()
    session.set_keyspace(KEYSPACE)
    return cluster, session


def cerrar_conexion(cluster, session):
    if session is not None:
        session.shutdown()

    if cluster is not None:
        cluster.shutdown()


def registrar_lectura_db(
    id_sensor,
    id_contenedor,
    temperatura=None,
    humedad=None,
    vibracion=None,
    gps_latitud=None,
    gps_longitud=None,
    bateria=None
):
    cluster = None
    session = None

    fecha_hora = datetime.now(timezone.utc)
    anio_mes = fecha_hora.strftime("%Y-%m")
    id_lectura = uuid4()

    try:
        cluster, session = abrir_conexion()

        insertar_sensor = session.prepare("""
            INSERT INTO lecturas_por_sensor (
                sensor_id, anio_mes, fecha_hora, id_lectura,
                temperatura, humedad, vibracion,
                gps_latitud, gps_longitud, bateria
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """)

        insertar_contenedor = session.prepare("""
            INSERT INTO lecturas_por_contenedor (
                contenedor_id, anio_mes, fecha_hora, id_lectura,
                sensor_id, temperatura, humedad, vibracion,
                gps_latitud, gps_longitud, bateria
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """)

        insertar_ultima = session.prepare("""
            INSERT INTO ultima_lectura_por_sensor (
                sensor_id, contenedor_id, fecha_hora, id_lectura,
                temperatura, humedad, vibracion,
                gps_latitud, gps_longitud, bateria
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """)

        valores = (
            temperatura,
            humedad,
            vibracion,
            gps_latitud,
            gps_longitud,
            bateria
        )

        # Agrupar las tres escrituras de una misma lectura IoT.
        batch = BatchStatement(
            batch_type=BatchType.LOGGED
        )

        # Guardar en el historial por sensor.
        batch.add(
            insertar_sensor,
            (
                int(id_sensor),
                anio_mes,
                fecha_hora,
                id_lectura,
                *valores
            )
        )

        # Guardar en el historial por contenedor.
        batch.add(
            insertar_contenedor,
            (
                int(id_contenedor),
                anio_mes,
                fecha_hora,
                id_lectura,
                int(id_sensor),
                *valores
            )
        )

        # Actualizar la última lectura del sensor.
        batch.add(
            insertar_ultima,
            (
                int(id_sensor),
                int(id_contenedor),
                fecha_hora,
                id_lectura,
                *valores
            )
        )

        # Ejecutar el batch en Cassandra.
        session.execute(batch)

        return id_lectura

    finally:
        cerrar_conexion(cluster, session)


def consultar_lecturas_sensor_db(id_sensor, anio_mes, limite=10):
    cluster = None
    session = None

    try:
        cluster, session = abrir_conexion()

        consulta = session.prepare("""
            SELECT *
            FROM lecturas_por_sensor
            WHERE sensor_id = ?
              AND anio_mes = ?
            LIMIT ?
        """)

        return list(session.execute(
            consulta,
            (int(id_sensor), anio_mes, int(limite))
        ))

    finally:
        cerrar_conexion(cluster, session)


def consultar_lecturas_contenedor_db(
    id_contenedor,
    anio_mes,
    limite=10
):
    cluster = None
    session = None

    try:
        cluster, session = abrir_conexion()

        consulta = session.prepare("""
            SELECT *
            FROM lecturas_por_contenedor
            WHERE contenedor_id = ?
              AND anio_mes = ?
            LIMIT ?
        """)

        return list(session.execute(
            consulta,
            (int(id_contenedor), anio_mes, int(limite))
        ))

    finally:
        cerrar_conexion(cluster, session)


def consultar_ultima_lectura_db(id_sensor):
    cluster = None
    session = None

    try:
        cluster, session = abrir_conexion()

        consulta = session.prepare("""
            SELECT *
            FROM ultima_lectura_por_sensor
            WHERE sensor_id = ?
        """)

        return session.execute(
            consulta,
            (int(id_sensor),)
        ).one()

    finally:
        cerrar_conexion(cluster, session)
