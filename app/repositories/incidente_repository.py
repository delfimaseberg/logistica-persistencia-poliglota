
from app.database.postgres_connection import get_postgres_connection


def crear_incidente(id_envio, tipo, severidad, descripcion, fecha=None):  # guarda un incidente Abierto; la usan la opción 1 de incidentes y la carga de ejemplo
    """fecha es opcional (carga histórica); por defecto, ahora."""
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                INSERT INTO incidente
                    (id_envio, tipo, severidad, estado, descripcion, fecha)
                VALUES (%s, %s, %s, 'Abierto', %s,
                        COALESCE(%s, CURRENT_TIMESTAMP))  -- sin fecha, se usa la de ahora
                RETURNING id_incidente
            """, (id_envio, tipo, severidad, descripcion, fecha))
            return cursor.fetchone()[0]


def listar_incidentes(id_envio=None, estado=None):  # incidentes con su ruta; la usa consultar incidentes
    consulta = """
        SELECT i.id_incidente, i.id_envio, i.tipo,
               i.fecha, i.severidad, i.estado, i.descripcion,
               e.origen, e.destino
        FROM incidente i
        JOIN envio e ON e.id_envio = i.id_envio
        WHERE 1 = 1  -- base para ir sumando filtros con AND
    """
    parametros = []

    if id_envio is not None:
        consulta += " AND i.id_envio = %s"
        parametros.append(id_envio)

    if estado is not None:
        consulta += " AND i.estado = %s"
        parametros.append(estado)

    consulta += " ORDER BY i.fecha DESC, i.id_incidente DESC"

    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute(consulta, parametros)
            return cursor.fetchall()


def buscar_incidente(id_incidente):  # un incidente por ID; lo usan actualizar y la vinculación con alertas
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT id_incidente, id_envio, tipo, fecha,
                       severidad, estado, descripcion
                FROM incidente
                WHERE id_incidente = %s
            """, (id_incidente,))
            return cursor.fetchone()


def actualizar_estado_incidente(id_incidente, estado):  # cambia el estado; la usa la opción 3 de incidentes
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                UPDATE incidente
                SET estado = %s
                WHERE id_incidente = %s
                  AND estado <> 'Cerrado'  -- un cerrado no se vuelve a abrir
            """, (estado, id_incidente))
            return cursor.rowcount > 0


def existe_incidente_por_lectura(  # busca un incidente por la marca de la lectura; la usa obtener_incidente_compatible
    id_envio, id_lectura, id_sensor=None, tipo=None
):
    marca = (  # marca que queda escrita en la descripción del incidente
        f"[iot:{id_sensor}:{id_lectura}:{tipo}]"
        if id_sensor is not None and tipo is not None
        else f"[lectura:{id_lectura}]"
    )

    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT id_incidente
                FROM incidente
                WHERE id_envio = %s
                  AND POSITION(%s IN descripcion) > 0  -- la descripción contiene la marca
                ORDER BY id_incidente
                LIMIT 1
            """, (id_envio, marca))

            fila = cursor.fetchone()
            return fila[0] if fila else None


def obtener_o_crear_incidente_iot(  # un solo incidente por envío, sensor, lectura y tipo; la usa procesar_incidente_de_alerta
    id_envio, id_sensor, id_lectura, tipo, severidad, descripcion
):
    marca = f"[iot:{id_sensor}:{id_lectura}:{tipo}]"
    detalle = f"{descripcion} | Sensor {id_sensor} {marca}"

    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute(  # candado por envío y marca: dos detecciones a la vez no crean dos incidentes
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (f"incidente-iot:{id_envio}:{marca}",)
            )

            cursor.execute("""
                SELECT id_incidente
                FROM incidente
                WHERE id_envio = %s
                  AND POSITION(%s IN descripcion) > 0
                ORDER BY id_incidente
                LIMIT 1
            """, (id_envio, marca))

            fila = cursor.fetchone()

            if fila:  # ya existía: se devuelve sin crear otro
                return fila[0], False

            cursor.execute("""
                INSERT INTO incidente
                    (id_envio, tipo, severidad, estado, descripcion)
                VALUES (%s, %s, %s, 'Abierto', %s)
                RETURNING id_incidente
            """, (id_envio, tipo, severidad, detalle))

            return cursor.fetchone()[0], True
