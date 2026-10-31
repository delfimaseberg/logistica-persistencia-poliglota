"""Consultas del portal de clientes: siempre filtradas por el cliente."""

from app.database.postgres_connection import get_postgres_connection


def listar_envios_cliente(id_cliente):
    """Envíos del cliente (mismas columnas que listar_envios)."""
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT e.id_envio, e.id_cliente, c.razon_social, e.origen,
                       e.destino, e.estado, e.prioridad, e.fecha_creacion,
                       e.fecha_entrega,
                       (SELECT MAX(t.fecha_estimada_llegada) FROM tramo t
                        WHERE t.id_envio = e.id_envio) AS llegada_estimada
                FROM envio e
                JOIN cliente c ON c.id_cliente = e.id_cliente
                WHERE e.id_cliente = %s
                ORDER BY e.fecha_creacion DESC, e.id_envio DESC
            """, (id_cliente,))
            return cursor.fetchall()
