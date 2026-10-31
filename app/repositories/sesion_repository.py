from app.database.postgres_connection import get_postgres_connection


def buscar_usuario_por_email(email):
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    u.id_usuario,
                    u.nombre,
                    u.apellido,
                    u.email,
                    u.contrasena_encriptada,
                    u.estado,
                    r.descripcion,
                    r.nivel_permisos
                FROM usuario u
                JOIN rol r
                    ON u.id_rol = r.id_rol
                WHERE LOWER(u.email) = LOWER(%s);
                """,
                (email,)
            )

            return cursor.fetchone()


def iniciar_sesion_db(id_usuario):
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO sesion (
                    id_usuario,
                    estado
                )
                SELECT
                    id_usuario,
                    'ACTIVA'
                FROM usuario
                WHERE id_usuario = %s
                  AND estado = 'ACTIVO'
                RETURNING id_sesion;
                """,
                (id_usuario,)
            )

            resultado = cursor.fetchone()

            if resultado is None:
                return None

            return resultado[0]


def listar_sesiones_activas():
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    s.id_sesion,
                    u.id_usuario,
                    u.nombre,
                    u.apellido,
                    u.email,
                    s.fecha_inicio,
                    CASE
                        WHEN u.id_cliente IS NOT NULL
                            THEN 'Cliente: ' || c.razon_social
                        WHEN u.id_proveedor IS NOT NULL
                            THEN 'Proveedor: ' || p.razon_social
                        WHEN u.id_operador IS NOT NULL
                            THEN 'Operador: ' || o.razon_social
                        ELSE 'Interno'
                    END AS parte
                FROM sesion s
                JOIN usuario u
                    ON s.id_usuario = u.id_usuario
                LEFT JOIN cliente c ON c.id_cliente = u.id_cliente
                LEFT JOIN proveedor p ON p.id_proveedor = u.id_proveedor
                LEFT JOIN operador_logistico o ON o.id_operador = u.id_operador
                WHERE s.estado = 'ACTIVA'
                  AND s.fecha_fin IS NULL
                ORDER BY s.fecha_inicio DESC;
                """
            )

            return cursor.fetchall()


def cerrar_sesion_db(id_sesion, id_usuario):
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                UPDATE sesion
                SET
                    estado = 'CERRADA',
                    fecha_fin = CURRENT_TIMESTAMP
                WHERE id_sesion = %s
                  AND id_usuario = %s
                  AND estado = 'ACTIVA'
                  AND fecha_fin IS NULL;
                """,
                (id_sesion, id_usuario)
            )

            return cursor.rowcount > 0

def cerrar_sesion_ajena_db(id_sesion, id_administrador):
    """Un administrador cierra la sesión activa de OTRO usuario.

    Queda registrado quién la cerró (sesion.cerrada_por, migración 015).
    """
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                UPDATE sesion
                SET
                    estado = 'CERRADA',
                    fecha_fin = CURRENT_TIMESTAMP,
                    cerrada_por = %s
                WHERE id_sesion = %s
                  AND id_usuario <> %s
                  AND estado = 'ACTIVA'
                  AND fecha_fin IS NULL;
                """,
                (id_administrador, id_sesion, id_administrador)
            )

            return cursor.rowcount > 0


def cerrada_por_otro(id_sesion):
    """True si la sesión la cerró un usuario distinto de su dueño."""
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute(
                "SELECT cerrada_por, id_usuario FROM sesion WHERE id_sesion = %s",
                (id_sesion,)
            )
            fila = cursor.fetchone()
            return bool(fila and fila[0] is not None and fila[0] != fila[1])
