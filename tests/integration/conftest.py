import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import psycopg
import pytest
from cassandra.cluster import Cluster
from neo4j import GraphDatabase
from pymongo import MongoClient


EXPECTED = {
    "POSTGRES_HOST": "127.0.0.1",
    "POSTGRES_PORT": "15432",
    "POSTGRES_DB": "logistica_poliglota_integration",
    "MONGO_URI": "mongodb://127.0.0.1:27018",
    "MONGO_DB": "logistica_poliglota_integration",
    "CASSANDRA_HOST": "127.0.0.1",
    "CASSANDRA_PORT": "19042",
    "CASSANDRA_KEYSPACE": "logistica_poliglota_integration",
    "NEO4J_URI": "bolt://127.0.0.1:17687",
    "NEO4J_DATABASE": "neo4j",
}


def _require_isolated_environment():
    if os.getenv("INTEGRATION_TESTS") != "1":
        pytest.exit(
            "Pruebas de integración bloqueadas: use scripts/run_integration_tests.ps1.",
            returncode=2,
        )

    mismatches = [
        key for key, expected in EXPECTED.items()
        if os.getenv(key) != expected
    ]
    if mismatches:
        pytest.exit(
            "Pruebas de integración bloqueadas: destinos no aislados o incompletos "
            f"({', '.join(mismatches)}).",
            returncode=2,
        )

    if os.getenv("NEO4J_USER") != "neo4j":
        pytest.exit("Pruebas bloqueadas: usuario Neo4j de integración inválido.", returncode=2)

    # Comprobación del destino real de PostgreSQL antes de cualquier fixture
    # que escriba datos sintéticos.
    try:
        with psycopg.connect(
            host=EXPECTED["POSTGRES_HOST"],
            port=EXPECTED["POSTGRES_PORT"],
            dbname=EXPECTED["POSTGRES_DB"],
            user=os.getenv("POSTGRES_USER"),
            password=os.getenv("POSTGRES_PASSWORD"),
            connect_timeout=3,
        ) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT current_database()")
                if cursor.fetchone()[0] != EXPECTED["POSTGRES_DB"]:
                    raise RuntimeError("PostgreSQL no confirmó la base de integración")
                cursor.execute(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema='public'"
                )
                tables = {row[0] for row in cursor.fetchall()}
                required_tables = {
                    "cliente", "envio", "tramo", "vehiculo", "contenedor",
                    "sensor_iot", "envio_contenedor", "usuario", "rol",
                    "incidente",
                }
                if not required_tables.issubset(tables):
                    raise RuntimeError("Faltan tablas del esquema PostgreSQL de integración")

        mongo = MongoClient(EXPECTED["MONGO_URI"], serverSelectionTimeoutMS=3000)
        mongo.admin.command("ping")
        if mongo[EXPECTED["MONGO_DB"]].name != EXPECTED["MONGO_DB"]:
            raise RuntimeError("MongoDB no confirmó la base de integración")
        required_collections = {
            "eventos_logisticos", "alertas", "mensajes", "grupos_trabajo",
            "predicciones_riesgo",
        }
        if not required_collections.issubset(
            set(mongo[EXPECTED["MONGO_DB"]].list_collection_names())
        ):
            raise RuntimeError("Faltan colecciones del esquema MongoDB de integración")
        mongo.close()

        cluster = Cluster(
            [EXPECTED["CASSANDRA_HOST"]],
            port=int(EXPECTED["CASSANDRA_PORT"]),
            connect_timeout=3,
        )
        session = cluster.connect()
        try:
            row = session.execute(
                "SELECT keyspace_name FROM system_schema.keyspaces "
                "WHERE keyspace_name=%s",
                (EXPECTED["CASSANDRA_KEYSPACE"],),
            ).one()
            if row is None or row.keyspace_name != EXPECTED["CASSANDRA_KEYSPACE"]:
                raise RuntimeError("Cassandra no confirmó el keyspace de integración")
            rows = session.execute(
                "SELECT table_name FROM system_schema.tables WHERE keyspace_name=%s",
                (EXPECTED["CASSANDRA_KEYSPACE"],),
            )
            tables = {row.table_name for row in rows}
            required_tables = {
                "lecturas_por_sensor", "lecturas_por_contenedor",
                "ultima_lectura_por_sensor",
            }
            if not required_tables.issubset(tables):
                raise RuntimeError("Faltan tablas del esquema Cassandra de integración")
        finally:
            session.shutdown()
            cluster.shutdown()

        driver = GraphDatabase.driver(
            EXPECTED["NEO4J_URI"],
            auth=(os.getenv("NEO4J_USER"), os.getenv("NEO4J_PASSWORD")),
        )
        try:
            with driver.session(database=EXPECTED["NEO4J_DATABASE"]) as session:
                row = session.run("CALL db.info() YIELD name RETURN name").single()
                if row is None or row["name"] != EXPECTED["NEO4J_DATABASE"]:
                    raise RuntimeError("Neo4j no confirmó la base de integración")
                constraints = {
                    record["name"]
                    for record in session.run("SHOW CONSTRAINTS YIELD name RETURN name")
                }
                if "envio_id_unique" not in constraints:
                    raise RuntimeError("Faltan restricciones del esquema Neo4j de integración")
        finally:
            driver.close()
    except Exception as error:
        pytest.exit(
            "Pruebas bloqueadas antes de escribir: no se pudo confirmar el stack "
            f"aislado ({type(error).__name__}).",
            returncode=2,
        )


@pytest.fixture(scope="session", autouse=True)
def integration_guard():
    _require_isolated_environment()


@pytest.fixture
def synthetic_logistics(integration_guard):
    from app.database.postgres_connection import get_postgres_connection
    from app.database.mongo_connection import get_mongo_database
    from app.repositories.grafo_repository import eliminar_envio_grafo
    from app.repositories.lectura_iot_repository import abrir_conexion, cerrar_conexion

    token = uuid4().hex[:12]
    cuit = f"9{uuid4().int % 10**12:012d}"
    now = datetime.now(timezone.utc)

    with get_postgres_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO cliente
                   (razon_social, cuit, email, pais, estado)
                   VALUES (%s, %s, %s, 'Argentina', 'Activo')
                   RETURNING id_cliente""",
                (f"IT cliente {token}", cuit, f"it-{token}@invalid.test"),
            )
            client_id = cursor.fetchone()[0]
            cursor.execute(
                "INSERT INTO rol (descripcion, nivel_permisos) VALUES (%s, 3) RETURNING id_rol",
                (f"IT rol {token}",),
            )
            role_id = cursor.fetchone()[0]
            user_ids = []
            for suffix in ("a", "b"):
                cursor.execute(
                    """INSERT INTO usuario
                       (id_cliente, id_rol, nombre, apellido, email,
                        contrasena_encriptada, estado)
                       VALUES (%s, %s, %s, 'Prueba', %s, 'test-only-hash', 'ACTIVO')
                       RETURNING id_usuario""",
                    (client_id, role_id, f"IT {suffix} {token}", f"it-{suffix}-{token}@invalid.test"),
                )
                user_ids.append(cursor.fetchone()[0])

            cursor.execute(
                """INSERT INTO envio
                   (id_cliente, origen, destino, estado, prioridad)
                   VALUES (%s, %s, %s, 'Pendiente', 'Alta')
                   RETURNING id_envio""",
                (client_id, f"Origen IT {token}", f"Destino IT {token}"),
            )
            shipment_id = cursor.fetchone()[0]
            cursor.execute(
                "INSERT INTO vehiculo (tipo, identificacion, empresa_operadora, estado) VALUES ('Camion', %s, %s, 'Activo') RETURNING id_vehiculo",
                (f"IT-{token}", f"Operadora IT {token}"),
            )
            vehicle_id = cursor.fetchone()[0]
            cursor.execute(
                "INSERT INTO contenedor (codigo_internacional, tipo, capacidad, estado) VALUES (%s, 'General', 10, 'Activo') RETURNING id_contenedor",
                (f"IT{token[:9]}",),
            )
            container_id = cursor.fetchone()[0]
            cursor.execute(
                "INSERT INTO sensor_iot (id_contenedor, tipo, fabricante, fecha_instalacion, estado) VALUES (%s, 'temperatura', 'IT', CURRENT_DATE, 'Activo') RETURNING id_sensor",
                (container_id,),
            )
            sensor_id = cursor.fetchone()[0]
            cursor.execute(
                "INSERT INTO envio_contenedor (id_envio, id_contenedor) VALUES (%s, %s)",
                (shipment_id, container_id),
            )
            cursor.execute(
                """INSERT INTO tramo
                   (id_envio, id_vehiculo, medio_transporte, origen, destino,
                    fecha_salida, fecha_estimada_llegada)
                   VALUES (%s, %s, 'Terrestre', %s, %s, %s, %s)""",
                (
                    shipment_id,
                    vehicle_id,
                    f"Origen IT {token}",
                    f"Destino IT {token}",
                    now,
                    now + timedelta(days=1),
                ),
            )

    data = {
        "token": token,
        "client_id": client_id,
        "role_id": role_id,
        "user_ids": user_ids,
        "shipment_id": shipment_id,
        "vehicle_id": vehicle_id,
        "container_id": container_id,
        "sensor_id": sensor_id,
        "month": now.strftime("%Y-%m"),
    }

    try:
        yield data
    finally:
        mongo = get_mongo_database()
        mongo["eventos_logisticos"].delete_many({"envio_id": shipment_id})
        mongo["predicciones_riesgo"].delete_many({"envio_id": shipment_id})
        mongo["alertas"].delete_many({"sensor_id": sensor_id})
        mongo["mensajes"].delete_many({
            "$or": [
                {"remitente_id": {"$in": user_ids}},
                {"destinatario_id": {"$in": user_ids}},
            ]
        })
        mongo["grupos_trabajo"].delete_many({"creador_id": user_ids[0]})

        cluster, session = abrir_conexion()
        try:
            session.execute(
                "DELETE FROM ultima_lectura_por_sensor WHERE sensor_id=%s",
                (sensor_id,),
            )
            session.execute(
                "DELETE FROM lecturas_por_sensor WHERE sensor_id=%s AND anio_mes=%s",
                (sensor_id, data["month"]),
            )
            session.execute(
                "DELETE FROM lecturas_por_contenedor WHERE contenedor_id=%s AND anio_mes=%s",
                (container_id, data["month"]),
            )
        finally:
            # Sesión compartida: cerrar_conexion no la cierra.
            cerrar_conexion(cluster, session)

        eliminar_envio_grafo(shipment_id)
        with get_postgres_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM incidente WHERE id_envio=%s", (shipment_id,))
                cursor.execute("DELETE FROM envio_contenedor WHERE id_envio=%s", (shipment_id,))
                cursor.execute("DELETE FROM tramo WHERE id_envio=%s", (shipment_id,))
                cursor.execute("DELETE FROM sensor_iot WHERE id_sensor=%s", (sensor_id,))
                cursor.execute("DELETE FROM contenedor WHERE id_contenedor=%s", (container_id,))
                cursor.execute("DELETE FROM vehiculo WHERE id_vehiculo=%s", (vehicle_id,))
                cursor.execute("DELETE FROM envio WHERE id_envio=%s", (shipment_id,))
                cursor.execute("DELETE FROM usuario WHERE id_usuario = ANY(%s)", (user_ids,))
                cursor.execute("DELETE FROM rol WHERE id_rol=%s", (role_id,))
                cursor.execute("DELETE FROM cliente WHERE id_cliente=%s", (client_id,))
