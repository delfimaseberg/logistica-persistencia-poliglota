
from app.database.postgres_connection import get_postgres_connection


def crear_sensor(sensor):
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                INSERT INTO sensor_iot (
                    id_contenedor, tipo, fabricante,
                    fecha_instalacion, estado
                )
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id_sensor
            """, (
                sensor.id_contenedor,
                sensor.tipo,
                sensor.fabricante,
                sensor.fecha_instalacion,
                sensor.estado
            ))
            return cursor.fetchone()[0]


def listar_sensores():
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT s.id_sensor, s.id_contenedor,
                       c.codigo_internacional, s.tipo,
                       s.fabricante, s.fecha_instalacion,
                       s.estado
                FROM sensor_iot s
                JOIN contenedor c
                    ON c.id_contenedor = s.id_contenedor
                ORDER BY s.id_sensor
            """)
            return cursor.fetchall()


def buscar_sensor_por_id(id_sensor):
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT s.id_sensor, s.id_contenedor,
                       c.codigo_internacional, s.tipo,
                       s.fabricante, s.fecha_instalacion,
                       s.estado
                FROM sensor_iot s
                JOIN contenedor c
                    ON c.id_contenedor = s.id_contenedor
                WHERE s.id_sensor = %s
            """, (id_sensor,))
            return cursor.fetchone()


def listar_sensores_por_contenedor(id_contenedor):
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT s.id_sensor, s.id_contenedor,
                       c.codigo_internacional, s.tipo,
                       s.fabricante, s.fecha_instalacion,
                       s.estado
                FROM sensor_iot s
                JOIN contenedor c
                    ON c.id_contenedor = s.id_contenedor
                WHERE s.id_contenedor = %s
                ORDER BY s.id_sensor
            """, (id_contenedor,))
            return cursor.fetchall()


def actualizar_sensor(id_sensor, sensor):
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                UPDATE sensor_iot
                SET id_contenedor = %s,
                    tipo = %s,
                    fabricante = %s,
                    fecha_instalacion = %s,
                    estado = %s
                WHERE id_sensor = %s
            """, (
                sensor.id_contenedor,
                sensor.tipo,
                sensor.fabricante,
                sensor.fecha_instalacion,
                sensor.estado,
                id_sensor
            ))
            return cursor.rowcount > 0


def eliminar_sensor_db(id_sensor):
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                DELETE FROM sensor_iot
                WHERE id_sensor = %s
            """, (id_sensor,))
            return cursor.rowcount > 0
