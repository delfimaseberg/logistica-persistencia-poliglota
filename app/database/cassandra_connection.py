import os
from cassandra.cluster import Cluster
from dotenv import load_dotenv

load_dotenv()

CASSANDRA_HOST = os.getenv("CASSANDRA_HOST")
CASSANDRA_PORT = int(os.getenv("CASSANDRA_PORT", "9042"))
CASSANDRA_KEYSPACE = os.getenv(
    "CASSANDRA_KEYSPACE", "logistica_poliglota"
)


def get_cassandra_session():
    cluster = Cluster(
        [CASSANDRA_HOST],
        port=CASSANDRA_PORT
    )

    session = cluster.connect()
    return cluster, session


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
