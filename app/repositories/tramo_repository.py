from app.database.postgres_connection import get_postgres_connection  # los tramos se guardan en PostgreSQL


def crear_tramo(tramo):  # inserta un tramo del envío; la usan "Registrar tramo" y la carga de datos de ejemplo
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                INSERT INTO tramo (  -- guarda el tramo con su vehículo, operador y fechas
                    id_envio,
                    id_vehiculo,
                    medio_transporte,
                    origen,
                    destino,
                    fecha_salida,
                    fecha_estimada_llegada,
                    id_operador
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)  -- un valor por columna, en el mismo orden
                RETURNING id_tramo  -- devuelve el ID que generó la base
            """, (
                tramo.id_envio,
                tramo.id_vehiculo,
                tramo.medio_transporte,
                tramo.origen,
                tramo.destino,
                tramo.fecha_salida,
                tramo.fecha_estimada_llegada,
                tramo.id_operador
            ))
            return cursor.fetchone()[0]


def listar_tramos_de_envio(id_envio):  # tramos de un envío con vehículo y operador; la usan "Registrar tramo", "Consultar tramos", "Modificar envío" y trazabilidad
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
                    t.fecha_estimada_llegada,
                    t.id_operador,
                    o.razon_social
                FROM tramo t
                JOIN vehiculo v  -- todo tramo tiene vehículo
                    ON t.id_vehiculo = v.id_vehiculo  -- para mostrar su identificación (patente, matrícula)
                LEFT JOIN operador_logistico o  -- LEFT porque los tramos viejos pueden no tener operador
                    ON o.id_operador = t.id_operador  -- trae la razón social del operador
                WHERE t.id_envio = %s  -- solo los tramos de ese envío
                ORDER BY t.fecha_salida, t.id_tramo  -- en el orden del recorrido: el último de la lista es el último tramo
            """, (id_envio,))
            return cursor.fetchall()

