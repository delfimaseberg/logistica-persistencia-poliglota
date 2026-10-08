from app.database.postgres_connection import get_postgres_connection


def obtener_clientes():
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT id_cliente, razon_social, cuit
                FROM cliente
                ORDER BY razon_social, id_cliente
            """)
            return cursor.fetchall()


def obtener_cliente_por_id(id_cliente):
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT id_cliente, razon_social, cuit
                FROM cliente
                WHERE id_cliente = %s
            """, (id_cliente,))
            return cursor.fetchone()


def crear_envio(envio):
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                INSERT INTO envio (
                    id_cliente, origen, destino, estado, prioridad
                )
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id_envio
            """, (
                envio.id_cliente,
                envio.origen,
                envio.destino,
                envio.estado,
                envio.prioridad
            ))
            return cursor.fetchone()[0]


def listar_envios():
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT
                    e.id_envio,
                    e.id_cliente,
                    c.razon_social,
                    e.origen,
                    e.destino,
                    e.estado,
                    e.prioridad,
                    e.fecha_creacion
                FROM envio e
                JOIN cliente c ON e.id_cliente = c.id_cliente
                ORDER BY e.id_envio
            """)
            return cursor.fetchall()


def buscar_envio_por_id(id_envio):
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT
                    e.id_envio,
                    e.id_cliente,
                    c.razon_social,
                    e.origen,
                    e.destino,
                    e.estado,
                    e.prioridad,
                    e.fecha_creacion
                FROM envio e
                JOIN cliente c ON e.id_cliente = c.id_cliente
                WHERE e.id_envio = %s
            """, (id_envio,))
            return cursor.fetchone()


def actualizar_envio(id_envio, envio):
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                UPDATE envio
                SET id_cliente = %s,
                    origen = %s,
                    destino = %s,
                    estado = %s,
                    prioridad = %s
                WHERE id_envio = %s
                  AND (
                    NOT EXISTS (
                      SELECT 1 FROM tramo t WHERE t.id_envio = envio.id_envio
                    )
                    OR (origen = %s AND destino = %s)
                  )
            """, (
                envio.id_cliente,
                envio.origen,
                envio.destino,
                envio.estado,
                envio.prioridad,
                id_envio,
                envio.origen,
                envio.destino
            ))
            return cursor.rowcount > 0


def eliminar_envio_db(id_envio):
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                DELETE FROM envio
                WHERE id_envio = %s
            """, (id_envio,))
            return cursor.rowcount > 0