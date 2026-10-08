from app.database.postgres_connection import get_postgres_connection


def crear_vehiculo(vehiculo):
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                INSERT INTO vehiculo (
                    tipo, identificacion, empresa_operadora, estado
                )
                VALUES (%s, %s, %s, %s)
                RETURNING id_vehiculo
            """, (
                vehiculo.tipo,
                vehiculo.identificacion,
                vehiculo.empresa_operadora,
                vehiculo.estado
            ))
            return cursor.fetchone()[0]


def listar_vehiculos():
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT id_vehiculo, tipo, identificacion,
                       empresa_operadora, estado
                FROM vehiculo
                ORDER BY id_vehiculo
            """)
            return cursor.fetchall()


def buscar_vehiculo_por_id(id_vehiculo):
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT id_vehiculo, tipo, identificacion,
                       empresa_operadora, estado
                FROM vehiculo
                WHERE id_vehiculo = %s
            """, (id_vehiculo,))
            return cursor.fetchone()


def buscar_vehiculo_por_identificacion(identificacion):
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT id_vehiculo, tipo, identificacion,
                       empresa_operadora, estado
                FROM vehiculo
                WHERE LOWER(identificacion) = LOWER(%s)
            """, (identificacion,))
            return cursor.fetchone()


def actualizar_vehiculo(id_vehiculo, vehiculo):
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                UPDATE vehiculo
                SET tipo = %s,
                    identificacion = %s,
                    empresa_operadora = %s,
                    estado = %s
                WHERE id_vehiculo = %s
            """, (
                vehiculo.tipo,
                vehiculo.identificacion,
                vehiculo.empresa_operadora,
                vehiculo.estado,
                id_vehiculo
            ))
            return cursor.rowcount > 0


def eliminar_vehiculo_db(id_vehiculo):
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                DELETE FROM vehiculo
                WHERE id_vehiculo = %s
            """, (id_vehiculo,))
            return cursor.rowcount > 0


def contar_tramos_de_vehiculo(id_vehiculo):
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT COUNT(*)
                FROM tramo
                WHERE id_vehiculo = %s
            """, (id_vehiculo,))
            return cursor.fetchone()[0]