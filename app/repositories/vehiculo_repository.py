from app.database.postgres_connection import get_postgres_connection


# Columnas: 0 id, 1 tipo, 2 identificación, 3 empresa_operadora (texto
# histórico), 4 estado, 5 id_operador, 6 razón social del operador.
_SELECT_VEHICULO = """
    SELECT v.id_vehiculo, v.tipo, v.identificacion,
           v.empresa_operadora, v.estado,
           v.id_operador, o.razon_social
    FROM vehiculo v
    LEFT JOIN operador_logistico o ON o.id_operador = v.id_operador
"""


def crear_vehiculo(vehiculo):
    # empresa_operadora ya no se escribe: el operador es id_operador.
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                INSERT INTO vehiculo (
                    tipo, identificacion, estado, id_operador
                )
                VALUES (%s, %s, %s, %s)
                RETURNING id_vehiculo
            """, (
                vehiculo.tipo,
                vehiculo.identificacion,
                vehiculo.estado,
                vehiculo.id_operador
            ))
            return cursor.fetchone()[0]


def listar_vehiculos():
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute(_SELECT_VEHICULO + " ORDER BY v.id_vehiculo")
            return cursor.fetchall()


def buscar_vehiculo_por_id(id_vehiculo):
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute(
                _SELECT_VEHICULO + " WHERE v.id_vehiculo = %s",
                (id_vehiculo,)
            )
            return cursor.fetchone()


def buscar_vehiculo_por_identificacion(identificacion):
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute(
                _SELECT_VEHICULO
                + " WHERE LOWER(v.identificacion) = LOWER(%s)",
                (identificacion,)
            )
            return cursor.fetchone()


def actualizar_vehiculo(id_vehiculo, vehiculo):
    # No toca empresa_operadora: el texto histórico se conserva tal cual.
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                UPDATE vehiculo
                SET tipo = %s,
                    identificacion = %s,
                    estado = %s,
                    id_operador = %s
                WHERE id_vehiculo = %s
            """, (
                vehiculo.tipo,
                vehiculo.identificacion,
                vehiculo.estado,
                vehiculo.id_operador,
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
