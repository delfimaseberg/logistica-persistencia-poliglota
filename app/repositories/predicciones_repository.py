
from datetime import datetime
from zoneinfo import ZoneInfo

from app.database.postgres_connection import get_postgres_connection
from app.database.mongo_connection import get_mongo_database
from pymongo import ReturnDocument


ZONA_PREDICCIONES = ZoneInfo("America/Argentina/Buenos_Aires")


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
                       e.fecha_creacion, c.razon_social,
                       e.origen, e.destino, e.pais_origen,
                       e.pais_destino, e.id_cliente
                FROM envio e
                JOIN cliente c ON c.id_cliente = e.id_cliente
                WHERE e.id_envio = %s
            """, (id_envio,))
            envio = cursor.fetchone()

            if envio is None:
                return None

            cursor.execute("""
                SELECT fecha_salida, fecha_estimada_llegada,
                       origen, destino
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
        "incidentes": incidentes,
        "origen": envio[5],
        "destino": envio[6],
        "pais_origen": envio[7],
        "pais_destino": envio[8],
        "id_cliente": envio[9],
    }


def envios_entregados_por_ruta():
    """Envíos entregados con su ruta, llegada estimada y entrega real.

    Base del historial de rutas que suelen atrasarse.
    """
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT e.id_envio, e.origen, e.destino,
                       MAX(t.fecha_estimada_llegada) AS llegada_estimada,
                       e.fecha_entrega
                FROM envio e
                LEFT JOIN tramo t ON t.id_envio = e.id_envio
                WHERE e.estado = 'Entregado'
                GROUP BY e.id_envio
                ORDER BY e.id_envio
            """)
            return cursor.fetchall()


def ultimas_predicciones(ids_envios=None):
    """La predicción más reciente de cada envío (de todos o de esos)."""
    filtro = {}
    if ids_envios is not None:
        filtro["envio_id"] = {"$in": [int(i) for i in ids_envios]}
    resultado = get_mongo_database()["predicciones_riesgo"].aggregate([
        {"$match": filtro},
        {"$sort": {"fecha_calculo": -1}},
        {"$group": {"_id": "$envio_id", "doc": {"$first": "$$ROOT"}}},
    ])
    return {fila["_id"]: fila["doc"] for fila in resultado}


def guardar_prediccion(prediccion):
    documento = dict(prediccion)
    fecha_calculo = documento.get("fecha_calculo")

    if not isinstance(fecha_calculo, datetime) or fecha_calculo.tzinfo is None:
        raise ValueError(
            "La fecha de cálculo debe ser un datetime con zona horaria."
        )

    envio_id = int(documento["envio_id"])
    dia_calculo = fecha_calculo.astimezone(
        ZONA_PREDICCIONES
    ).date().isoformat()
    documento["envio_id"] = envio_id
    documento["dia_calculo"] = dia_calculo

    coleccion = get_mongo_database()["predicciones_riesgo"]
    resultado = coleccion.find_one_and_update(
        {"envio_id": envio_id, "dia_calculo": dia_calculo},
        {"$set": documento},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return str(resultado["_id"])


def obtener_historial_predicciones(id_envio, limite=10):
    return list(
        get_mongo_database()["predicciones_riesgo"]
        .find({"envio_id": int(id_envio)})
        .sort("fecha_calculo", -1)
        .limit(limite)
    )


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
