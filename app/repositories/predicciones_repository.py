
from datetime import datetime, timezone

from app.database.postgres_connection import get_postgres_connection
from app.database.mongo_connection import get_mongo_database


def listar_envios_analisis():
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT e.id_envio, c.razon_social, e.origen,
                       e.destino, e.estado, e.prioridad,
                       e.fecha_creacion
                FROM envio e
                JOIN cliente c ON c.id_cliente = e.id_cliente
                ORDER BY e.id_envio
            """)
            return cursor.fetchall()


def obtener_datos_riesgo(id_envio):
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT e.id_envio, e.estado, e.prioridad,
                       e.fecha_creacion, c.razon_social
                FROM envio e
                JOIN cliente c ON c.id_cliente = e.id_cliente
                WHERE e.id_envio = %s
            """, (id_envio,))
            envio = cursor.fetchone()

            if envio is None:
                return None

            cursor.execute("""
                SELECT fecha_salida, fecha_estimada_llegada
                FROM tramo
                WHERE id_envio = %s
                ORDER BY fecha_salida, id_tramo
            """, (id_envio,))
            tramos = cursor.fetchall()

            cursor.execute("""
                SELECT severidad, estado
                FROM incidente
                WHERE id_envio = %s
            """, (id_envio,))
            incidentes = cursor.fetchall()

    return {
        "envio_id": envio[0],
        "estado": envio[1],
        "prioridad": envio[2],
        "fecha_creacion": envio[3],
        "cliente": envio[4],
        "tramos": tramos,
        "incidentes": incidentes
    }


def guardar_prediccion(prediccion):
    coleccion = get_mongo_database()["predicciones_riesgo"]
    coleccion.create_index(
        [("envio_id", 1), ("fecha_calculo", -1)],
        name="idx_predicciones_envio_fecha"
    )
    resultado = coleccion.insert_one(prediccion)
    return str(resultado.inserted_id)


def obtener_historial_predicciones(id_envio, limite=10):
    return list(
        get_mongo_database()["predicciones_riesgo"]
        .find({"envio_id": int(id_envio)})
        .sort("fecha_calculo", -1)
        .limit(limite)
    )


def reporte_clientes_por_envios():
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT c.razon_social, COUNT(e.id_envio) AS cantidad
                FROM cliente c
                JOIN envio e ON e.id_cliente = c.id_cliente
                GROUP BY c.id_cliente, c.razon_social
                ORDER BY cantidad DESC, c.razon_social
                LIMIT 20
            """)
            return cursor.fetchall()


def reporte_historico_incidentes():
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT c.razon_social,
                       COUNT(DISTINCT e.id_envio) AS envios,
                       COUNT(i.id_incidente) AS incidentes,
                       COUNT(i.id_incidente) FILTER (
                           WHERE LOWER(i.estado) NOT IN
                           ('cerrado', 'resuelto')
                       ) AS incidentes_abiertos
                FROM cliente c
                JOIN envio e ON e.id_cliente = c.id_cliente
                LEFT JOIN incidente i ON i.id_envio = e.id_envio
                GROUP BY c.id_cliente, c.razon_social
                ORDER BY incidentes DESC, c.razon_social
            """)
            return cursor.fetchall()


def reporte_demoras_estimadas():
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT e.id_envio, c.razon_social, e.estado,
                       MAX(t.fecha_estimada_llegada) AS llegada_estimada
                FROM envio e
                JOIN cliente c ON c.id_cliente = e.id_cliente
                JOIN tramo t ON t.id_envio = e.id_envio
                WHERE LOWER(e.estado) NOT IN
                      ('entregado', 'cancelado')
                GROUP BY e.id_envio, c.razon_social, e.estado
                HAVING MAX(t.fecha_estimada_llegada)
                       < CURRENT_TIMESTAMP
                ORDER BY llegada_estimada
            """)
            return cursor.fetchall()
