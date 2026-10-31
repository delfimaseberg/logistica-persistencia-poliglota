from app.database.postgres_connection import get_postgres_connection


def asociar_contenedor_db(id_envio, id_contenedor):
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                INSERT INTO envio_contenedor (
                    id_envio, id_contenedor
                )
                SELECT e.id_envio, c.id_contenedor
                FROM envio e
                JOIN contenedor c
                    ON c.id_contenedor = %s
                WHERE e.id_envio = %s
                  AND e.estado NOT IN ('Cancelado', 'Entregado')
                  AND c.estado = 'Disponible'
                  AND NOT EXISTS (
                      SELECT 1
                      FROM envio_contenedor ec
                      WHERE ec.id_contenedor = c.id_contenedor
                  )
                ON CONFLICT DO NOTHING
                RETURNING id_envio
            """, (id_contenedor, id_envio))

            asociado = cursor.fetchone() is not None

            if asociado:
                # Si el contenedor vuelve a viajar, se reactivan los sensores
                # que se apagaron por la entrega de un envío anterior (no los
                # inactivos por otros motivos).
                cursor.execute("""
                    UPDATE sensor_iot
                    SET estado = 'Activo', motivo_inactivo = NULL
                    WHERE id_contenedor = %s
                      AND estado = 'Inactivo'
                      AND motivo_inactivo LIKE 'Entrega del envío %%'
                """, (id_contenedor,))

            return asociado


def listar_contenedores_de_envio(id_envio):
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT c.id_contenedor, c.codigo_internacional,
                       c.tipo, c.capacidad, c.estado
                FROM envio_contenedor ec
                JOIN contenedor c
                    ON ec.id_contenedor = c.id_contenedor
                WHERE ec.id_envio = %s
                ORDER BY c.id_contenedor
            """, (id_envio,))
            return cursor.fetchall()


def buscar_asociacion(id_envio, id_contenedor):
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT 1
                FROM envio_contenedor
                WHERE id_envio = %s
                  AND id_contenedor = %s
            """, (id_envio, id_contenedor))
            return cursor.fetchone() is not None


def desasociar_contenedor_db(id_envio, id_contenedor):
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                DELETE FROM envio_contenedor
                WHERE id_envio = %s
                  AND id_contenedor = %s
            """, (id_envio, id_contenedor))
            return cursor.rowcount > 0