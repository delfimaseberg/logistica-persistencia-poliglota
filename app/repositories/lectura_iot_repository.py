from datetime import datetime, timedelta, timezone
from threading import Lock
from uuid import uuid4

from cassandra.query import BatchStatement, BatchType

from app.database.cassandra_connection import (
    CASSANDRA_KEYSPACE,
    obtener_sesion_cassandra,
)


KEYSPACE = CASSANDRA_KEYSPACE  # keyspace de Cassandra donde están las lecturas

# Sentencias preparadas una sola vez por sesión (preparar en cada operación
# es un viaje extra al servidor).
_preparadas = {}  # caché de sentencias preparadas
_lock_preparadas = Lock()


def _preparar(session, cql):  # prepara cada CQL una sola vez; la usan todas las funciones de acá
    clave = (id(session), cql)
    with _lock_preparadas:
        if clave not in _preparadas:
            _preparadas[clave] = session.prepare(cql)
        return _preparadas[clave]


def abrir_conexion():  # sesión de Cassandra compartida; la usan este archivo y recorrido_repository
    """Devuelve (None, sesión compartida).

    Se conserva la firma anterior (cluster, session) para los llamadores
    existentes; el cluster es None porque la sesión no les pertenece.
    """
    return None, obtener_sesion_cassandra()


def cerrar_conexion(cluster, session):  # no cierra la sesión compartida
    """No cierra la sesión compartida (se cierra al terminar el proceso).

    Solo cierra conexiones propias que alguien haya abierto aparte.
    """
    if cluster is None:
        return

    if session is not None:
        session.shutdown()
    cluster.shutdown()


_INSERTAR_SENSOR = """
    INSERT INTO lecturas_por_sensor (  -- historial por sensor: partición sensor y mes
        sensor_id, anio_mes, fecha_hora, id_lectura,
        temperatura, humedad, vibracion,
        gps_latitud, gps_longitud, bateria
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_INSERTAR_CONTENEDOR = """
    INSERT INTO lecturas_por_contenedor (  -- historial por contenedor: partición contenedor y mes
        contenedor_id, anio_mes, fecha_hora, id_lectura,
        sensor_id, temperatura, humedad, vibracion,
        gps_latitud, gps_longitud, bateria
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_INSERTAR_ULTIMA = """
    INSERT INTO ultima_lectura_por_sensor (  -- una fila por sensor: cada lectura nueva la pisa
        sensor_id, contenedor_id, fecha_hora, id_lectura,
        temperatura, humedad, vibracion,
        gps_latitud, gps_longitud, bateria
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


def registrar_lectura_db(  # guarda una lectura en las tres tablas; la usan carga manual, simulaciones, monitoreo y la carga de ejemplo
    id_sensor,
    id_contenedor,
    temperatura=None,
    humedad=None,
    vibracion=None,
    gps_latitud=None,
    gps_longitud=None,
    bateria=None,
    fecha_hora=None
):
    """Registra una lectura en las tres tablas (batch LOGGED).

    fecha_hora es opcional (carga histórica); por defecto, ahora.
    La partición (anio_mes) se calcula de la fecha de la lectura.
    """
    if fecha_hora is None:
        fecha_hora = datetime.now(timezone.utc)
    elif fecha_hora.tzinfo is None:
        raise ValueError("La fecha de la lectura debe tener zona horaria.")
    fecha_hora = fecha_hora.astimezone(timezone.utc)  # en Cassandra todo se guarda en UTC

    anio_mes = fecha_hora.strftime("%Y-%m")  # partición por mes, para que no crezcan sin límite
    id_lectura = uuid4()  # mismo id de lectura en las tres tablas

    _, session = abrir_conexion()

    valores = (
        temperatura,
        humedad,
        vibracion,
        gps_latitud,
        gps_longitud,
        bateria
    )

    # Agrupar las tres escrituras de una misma lectura IoT.
    batch = BatchStatement(batch_type=BatchType.LOGGED)  # batch LOGGED: se escriben las tres o ninguna

    # Historial por sensor.
    batch.add(
        _preparar(session, _INSERTAR_SENSOR),
        (int(id_sensor), anio_mes, fecha_hora, id_lectura, *valores)
    )

    # Historial por contenedor.
    batch.add(
        _preparar(session, _INSERTAR_CONTENEDOR),
        (int(id_contenedor), anio_mes, fecha_hora, id_lectura,
         int(id_sensor), *valores)
    )

    # Última lectura del sensor.
    batch.add(
        _preparar(session, _INSERTAR_ULTIMA),
        (int(id_sensor), int(id_contenedor), fecha_hora, id_lectura, *valores)
    )

    session.execute(batch)  # una sola ida a Cassandra

    return id_lectura


def existe_lectura_sensor(id_sensor, fecha_hora):  # si ya hay una lectura en ese instante; la usa la carga de ejemplo para no duplicar
    """True si el sensor ya tiene una lectura en esa fecha y hora exactas.

    La clave de lecturas_por_sensor es ((sensor_id, anio_mes), fecha_hora,
    id_lectura) e id_lectura es un UUID aleatorio, así que reinsertar la
    misma lectura NO la sobrescribe: crearía otra fila. Esta consulta por
    clave de partición + columna de clustering permite no duplicar.
    """
    fecha_hora = fecha_hora.astimezone(timezone.utc)
    _, session = abrir_conexion()
    consulta = _preparar(session, """
        SELECT id_lectura
        FROM lecturas_por_sensor
        WHERE sensor_id = ?
          AND anio_mes = ?
          AND fecha_hora = ?  -- clave de partición más la columna de clustering
        LIMIT 1
    """)
    return session.execute(
        consulta,
        (int(id_sensor), fecha_hora.strftime("%Y-%m"), fecha_hora)
    ).one() is not None


def consultar_lecturas_sensor_db(  # lecturas de un sensor en un mes; la usan la opción 2 de monitoreo y la consulta GPS
    id_sensor,
    anio_mes,
    limite=10
):
    _, session = abrir_conexion()

    consulta = _preparar(session, """
        SELECT *
        FROM lecturas_por_sensor
        WHERE sensor_id = ?
          AND anio_mes = ?  -- siempre con la partición completa: sensor y mes
        LIMIT ?
    """)

    return list(session.execute(
        consulta,
        (int(id_sensor), anio_mes, int(limite))
    ))


def consultar_lecturas_contenedor_db(  # lecturas de un contenedor en un mes; la usa la opción 3 de monitoreo
    id_contenedor,
    anio_mes,
    limite=10
):
    _, session = abrir_conexion()

    consulta = _preparar(session, """
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


def consultar_ultima_lectura_db(id_sensor):  # la última lectura de un sensor; la usan monitoreo, sensores y detección de sensores sin lecturas
    _, session = abrir_conexion()

    consulta = _preparar(session, """
        SELECT *
        FROM ultima_lectura_por_sensor
        WHERE sensor_id = ?
    """)

    return session.execute(
        consulta,
        (int(id_sensor),)
    ).one()


def ultimas_lecturas_sensor(id_sensor, cantidad, ahora=None):  # últimas N lecturas de un sensor; la usa la detección de fallas en incidentes
    """Las últimas lecturas del sensor, de la más nueva a la más vieja.

    Busca en la partición del mes actual y, si faltan, en la del mes anterior.
    """
    ahora = (ahora or datetime.now(timezone.utc)).astimezone(timezone.utc)
    anterior = (ahora.replace(day=1) - timedelta(days=1))
    lecturas = []
    for anio_mes in (ahora.strftime("%Y-%m"), anterior.strftime("%Y-%m")):  # mes actual y, si no alcanza, el anterior
        lecturas.extend(consultar_lecturas_sensor_db(id_sensor, anio_mes, cantidad - len(lecturas)))
        if len(lecturas) >= cantidad:
            break
    return lecturas[:cantidad]


def meses_entre(desde, hasta):  # lista de meses AAAA-MM de un período; la usa la consulta por período
    """Particiones 'AAAA-MM' que cubren el intervalo [desde, hasta]."""
    meses = []
    anio, mes = desde.year, desde.month
    while (anio, mes) <= (hasta.year, hasta.month):
        meses.append(f"{anio:04d}-{mes:02d}")
        anio, mes = (anio + 1, 1) if mes == 12 else (anio, mes + 1)
    return meses


def consultar_lecturas_contenedor_periodo(id_contenedor, desde, hasta):  # lecturas de un contenedor entre dos fechas; la usa el reporte cobrable de condiciones de carga
    """Lecturas de un contenedor entre dos instantes (con zona horaria).

    Consulta una partición (contenedor, mes) por cada mes del intervalo y
    filtra por la columna de clustering fecha_hora.
    """
    desde = desde.astimezone(timezone.utc)
    hasta = hasta.astimezone(timezone.utc)
    _, session = abrir_conexion()
    consulta = _preparar(session, """
        SELECT *
        FROM lecturas_por_contenedor
        WHERE contenedor_id = ?
          AND anio_mes = ?
          AND fecha_hora >= ?  -- rango sobre la columna de clustering
          AND fecha_hora < ?
    """)
    lecturas = []
    for anio_mes in meses_entre(desde, hasta):  # una consulta por cada mes del período
        lecturas.extend(session.execute(
            consulta, (int(id_contenedor), anio_mes, desde, hasta)
        ))
    lecturas.sort(key=lambda lectura: lectura.fecha_hora)
    return lecturas
