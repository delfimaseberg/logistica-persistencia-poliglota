from app.database.postgres_connection import get_postgres_connection  # todas las consultas de envíos van a PostgreSQL


def obtener_clientes():  # clientes para elegir a quién pertenece el envío; la usa seleccionar_cliente (registrar y modificar envío)
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT id_cliente, razon_social, cuit
                FROM cliente
                ORDER BY razon_social, id_cliente  -- ordenados por nombre para mostrarlos en pantalla
            """)
            return cursor.fetchall()


def obtener_cliente_por_id(id_cliente):  # trae un cliente por ID; seleccionar_cliente la usa para confirmar que el ID existe
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT id_cliente, razon_social, cuit
                FROM cliente
                WHERE id_cliente = %s  -- solo el cliente que se eligió
            """, (id_cliente,))
            return cursor.fetchone()


def crear_envio(envio, fecha_creacion=None):  # inserta el envío; la usan "Registrar envío" y la carga de datos de ejemplo
    """fecha_creacion es opcional (carga histórica); por defecto, ahora."""
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                INSERT INTO envio (  -- guarda el envío con sus países de origen y destino
                    id_cliente, origen, destino, estado, prioridad,
                    fecha_creacion, pais_origen, pais_destino
                )
                VALUES (%s, %s, %s, %s, %s,
                        COALESCE(%s, CURRENT_TIMESTAMP), %s, %s)  -- si no viene fecha de creación, usa la de ahora
                RETURNING id_envio  -- devuelve el ID que generó la base
            """, (
                envio.id_cliente,
                envio.origen,
                envio.destino,
                envio.estado,
                envio.prioridad,
                fecha_creacion,
                envio.pais_origen,
                envio.pais_destino
            ))
            return cursor.fetchone()[0]


def listar_envios():  # todos los envíos con la razón social del cliente; la usa "Listar envíos"
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
                    e.fecha_creacion,
                    e.fecha_entrega,
                    e.pais_origen,
                    e.pais_destino
                FROM envio e
                JOIN cliente c ON e.id_cliente = c.id_cliente  -- une con cliente para mostrar la razón social
                ORDER BY e.id_envio  -- del más viejo al más nuevo
            """)
            return cursor.fetchall()


def buscar_envio_por_id(id_envio):  # un envío con su cliente; la usan buscar, modificar y eliminar envío, tramos, contenedores, incidentes, trazabilidad y el portal del cliente
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
                    e.fecha_creacion,
                    e.fecha_entrega,
                    e.pais_origen,
                    e.pais_destino
                FROM envio e
                JOIN cliente c ON e.id_cliente = c.id_cliente
                WHERE e.id_envio = %s  -- solo el envío pedido
            """, (id_envio,))
            return cursor.fetchone()  # None si el envío no existe


def actualizar_envio(id_envio, envio):  # actualiza cliente, ruta, estado y prioridad; la usa "Modificar envío" (y la carga de ejemplo)
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                UPDATE envio
                SET id_cliente = %s,
                    origen = %s,
                    destino = %s,
                    estado = %s,
                    prioridad = %s
                WHERE id_envio = %s  -- el envío que se modifica
                  AND (  -- y además tiene que cumplirse una de estas dos condiciones:
                    NOT EXISTS (  -- que el envío todavía no tenga tramos
                      SELECT 1 FROM tramo t WHERE t.id_envio = envio.id_envio  -- busca algún tramo de este envío
                    )
                    OR (origen = %s AND destino = %s)  -- o que no cambien el origen ni el destino, así no queda desarmada la ruta de los tramos
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
            return cursor.rowcount > 0  # False si no existe o si se quiso cambiar la ruta de un envío con tramos


def eliminar_envio_db(id_envio):  # borra el envío; la usa "Eliminar envío" (si tiene tramos o contenedores, la base no lo deja)
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                DELETE FROM envio
                WHERE id_envio = %s  -- solo ese envío
            """, (id_envio,))
            return cursor.rowcount > 0  # True si lo borró


def actualizar_paises_envio(id_envio, pais_origen, pais_destino):  # cambia solo los países; la usa la opción 6 de "Modificar envío" (y la carga de ejemplo)
    """Completa o corrige los países de un envío (también los anteriores a 014)."""
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                UPDATE envio
                SET pais_origen = %s, pais_destino = %s  -- solo los países, lo demás queda igual
                WHERE id_envio = %s  -- del envío elegido
            """, (pais_origen, pais_destino, id_envio))
            return cursor.rowcount > 0
