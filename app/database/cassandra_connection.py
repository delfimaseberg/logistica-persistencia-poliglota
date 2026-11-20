import atexit
import os
import threading

from cassandra.cluster import Cluster
from dotenv import load_dotenv

load_dotenv()

CASSANDRA_HOST = os.getenv("CASSANDRA_HOST")
CASSANDRA_PORT = int(os.getenv("CASSANDRA_PORT", "9042"))
CASSANDRA_KEYSPACE = os.getenv(
    "CASSANDRA_KEYSPACE", "logistica_poliglota"
)


def get_cassandra_session():
    """Conexión nueva e independiente (solo para pruebas de conexión).

    Las operaciones de la aplicación usan obtener_sesion_cassandra().
    """
    cluster = Cluster(
        [CASSANDRA_HOST],
        port=CASSANDRA_PORT
    )

    session = cluster.connect()
    return cluster, session


# Sesión compartida
#
# Abrir un Cluster por operación agota conexiones con volumen (por ejemplo,
# el registro continuo de lecturas). El driver de Cassandra está pensado
# para una sesión por proceso: es thread-safe, mantiene su propio pool y se
# reconecta sola. Se crea la primera vez que se usa y se cierra al salir.


_cluster = None
_session = None
_lock = threading.Lock()


def obtener_sesion_cassandra(): # crea la sesion la 1era vez, ya conectada al keyspace del proyecto y dsp devuelve siempre la misma

    global _cluster, _session

    with _lock:
        if _session is None or _session.is_shutdown:
            if _cluster is not None:
                _cluster.shutdown()
            _cluster = Cluster([CASSANDRA_HOST], port=CASSANDRA_PORT)
            _session = _cluster.connect(CASSANDRA_KEYSPACE)
        return _session


def cerrar_sesion_cassandra():
    """Cierra la sesión compartida (se llama sola al terminar el proceso)."""
    global _cluster, _session

    with _lock:
        if _cluster is not None:
            _cluster.shutdown()
        _cluster = None
        _session = None


atexit.register(cerrar_sesion_cassandra) # la cierra sola cuando termina el programa


def probar_conexion_cassandra():
    cluster = None
    session = None

    try:
        cluster, session = get_cassandra_session()

        resultado = session.execute(
            "SELECT cluster_name FROM system.local;"
        ).one()

        print(
            f"Conexión a Cassandra exitosa. "
            f"Cluster: {resultado.cluster_name}"
        )

    except Exception as e:
        print(f"Error al conectar con Cassandra: {e}")

    finally:
        if session:
            session.shutdown()

        if cluster:
            cluster.shutdown()
