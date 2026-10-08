from app.database.postgres_connection import get_postgres_connection


def crear_tramo(tramo):
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                INSERT INTO tramo (
                    id_envio,
                    id_vehiculo,
                    medio_transporte,
                    origen,
                    destino,
                    fecha_salida,
                    fecha_estimada_llegada
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id_tramo
            """, (
                tramo.id_envio,
                tramo.id_vehiculo,
                tramo.medio_transporte,
                tramo.origen,
                tramo.destino,
                tramo.fecha_salida,
                tramo.fecha_estimada_llegada
            ))
            return cursor.fetchone()[0]


def listar_tramos_de_envio(id_envio):
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT
                    t.id_tramo,
                    t.id_envio,
                    t.id_vehiculo,
                    v.identificacion,
                    t.medio_transporte,
                    t.origen,
                    t.destino,
                    t.fecha_salida,
                    t.fecha_estimada_llegada
                FROM tramo t
                JOIN vehiculo v
                    ON t.id_vehiculo = v.id_vehiculo
                WHERE t.id_envio = %s
                ORDER BY t.fecha_salida, t.id_tramo
            """, (id_envio,))
            return cursor.fetchall()


def buscar_tramo_por_id(id_tramo):
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT
                    id_tramo, id_envio, id_vehiculo,
                    medio_transporte, origen, destino,
                    fecha_salida, fecha_estimada_llegada
                FROM tramo
                WHERE id_tramo = %s
            """, (id_tramo,))
            return cursor.fetchone()