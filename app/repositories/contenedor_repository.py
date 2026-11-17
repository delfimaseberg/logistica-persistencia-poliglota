from app.database.postgres_connection import get_postgres_connection


def crear_contenedor(contenedor):  # guarda un contenedor y devuelve su ID; la usa registrar_contenedor
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                INSERT INTO contenedor (
                    codigo_internacional, tipo, capacidad, estado
                )
                VALUES (%s, %s, %s, %s)
                RETURNING id_contenedor
            """, (
                contenedor.codigo_internacional,
                contenedor.tipo,
                contenedor.capacidad,
                contenedor.estado
            ))
            return cursor.fetchone()[0]


def listar_contenedores():  # todos los contenedores; la usan el listado y la elección de contenedor al cargar un sensor
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT id_contenedor, codigo_internacional,
                       tipo, capacidad, estado
                FROM contenedor
                ORDER BY id_contenedor
            """)
            return cursor.fetchall()


def buscar_contenedor_por_id(id_contenedor):  # un contenedor por ID; lo usan contenedores, sensores, envíos y lecturas
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT id_contenedor, codigo_internacional,
                       tipo, capacidad, estado
                FROM contenedor
                WHERE id_contenedor = %s
            """, (id_contenedor,))
            return cursor.fetchone()


def buscar_contenedor_por_codigo(codigo):  # busca por código para no repetirlo; la usa pedir_codigo
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT id_contenedor, codigo_internacional,
                       tipo, capacidad, estado
                FROM contenedor
                WHERE UPPER(codigo_internacional) = UPPER(%s)  -- sin importar mayúsculas
            """, (codigo,))
            return cursor.fetchone()


def actualizar_contenedor(id_contenedor, contenedor):  # guarda los cambios; la usa modificar_contenedor_service
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                UPDATE contenedor
                SET codigo_internacional = %s,
                    tipo = %s,
                    capacidad = %s,
                    estado = %s
                WHERE id_contenedor = %s
            """, (
                contenedor.codigo_internacional,
                contenedor.tipo,
                contenedor.capacidad,
                contenedor.estado,
                id_contenedor
            ))
            return cursor.rowcount > 0


def eliminar_contenedor_db(id_contenedor):  # borra el contenedor; la usa eliminar_contenedor_service
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                DELETE FROM contenedor
                WHERE id_contenedor = %s
            """, (id_contenedor,))
            return cursor.rowcount > 0


def contar_asociaciones_contenedor(id_contenedor):  # en cuántos envíos está; la usan modificar y eliminar contenedor
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT COUNT(*)
                FROM envio_contenedor
                WHERE id_contenedor = %s
            """, (id_contenedor,))
            return cursor.fetchone()[0]


def contar_sensores_contenedor(id_contenedor):  # cuántos sensores tiene; la usa eliminar contenedor
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT COUNT(*)
                FROM sensor_iot
                WHERE id_contenedor = %s
            """, (id_contenedor,))
            return cursor.fetchone()[0]


def listar_contenedores_disponibles():  # contenedores libres para asignar; la usa "Asociar contenedor a envío"
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT c.id_contenedor, c.codigo_internacional,
                       c.tipo, c.capacidad, c.estado
                FROM contenedor c
                WHERE LOWER(c.estado) = LOWER('Disponible')
                  AND NOT EXISTS (  -- que no estén asignados a ningún envío
                      SELECT 1
                      FROM envio_contenedor ec
                      WHERE ec.id_contenedor = c.id_contenedor
                  )
                ORDER BY c.id_contenedor
            """)
            return cursor.fetchall()