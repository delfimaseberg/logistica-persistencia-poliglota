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
                    s.fecha_inicio
                FROM sesion s
                JOIN usuario u
                    ON s.id_usuario = u.id_usuario
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