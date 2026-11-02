from psycopg import errors

from app.database.postgres_connection import get_postgres_connection
from app.utils.validaciones_datos import validar_datos_usuario


EMAIL_REPETIDO = "Ya existe un usuario con ese email."

# Columnas de listar/buscar. 0-10 como antes; 11-13 desde la migración 016.
_SELECT_USUARIO = """
    SELECT
        u.id_usuario,
        u.id_cliente,
        u.id_rol,
        u.nombre,
        u.apellido,
        u.email,
        u.estado,
        u.fecha_registro,
        u.id_proveedor,
        u.id_operador,
        COALESCE(
            c.razon_social, p.razon_social, o.razon_social
        ) AS nombre_parte,
        CASE WHEN u.bloqueado_hasta > now() THEN u.bloqueado_hasta END AS bloqueado_hasta,
        u.intentos_fallidos,
        u.debe_cambiar_contrasena
    FROM usuario u
    LEFT JOIN cliente c ON c.id_cliente = u.id_cliente
    LEFT JOIN proveedor p ON p.id_proveedor = u.id_proveedor
    LEFT JOIN operador_logistico o
        ON o.id_operador = u.id_operador
"""


def _validar(usuario):
    usuario.nombre, usuario.apellido, usuario.email = validar_datos_usuario(
        usuario.nombre, usuario.apellido, usuario.email
    )


def crear_usuario(usuario):
    """Alta. La contraseña llega ya convertida en hash (nunca en texto)."""
    _validar(usuario)
    conexion = get_postgres_connection()

    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO usuario
                    (
                        id_cliente,
                        id_rol,
                        nombre,
                        apellido,
                        email,
                        contrasena_encriptada,
                        estado,
                        id_proveedor,
                        id_operador
                    )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id_usuario;
                """,
                (
                    usuario.id_cliente,
                    usuario.id_rol,
                    usuario.nombre,
                    usuario.apellido,
                    usuario.email,
                    usuario.contrasena_encriptada,
                    usuario.estado,
                    usuario.id_proveedor,
                    usuario.id_operador
                )
            )

            id_usuario = cursor.fetchone()[0]

        conexion.commit()
        return id_usuario

    except errors.UniqueViolation:
        conexion.rollback()
        raise ValueError(EMAIL_REPETIDO) from None

    except Exception:
        conexion.rollback()
        raise

    finally:
        conexion.close()


def listar_usuarios():
    conexion = get_postgres_connection()

    try:
        with conexion.cursor() as cursor:
            cursor.execute(_SELECT_USUARIO + " ORDER BY u.id_usuario;")
            return cursor.fetchall()

    finally:
        conexion.close()


def buscar_usuario_por_id(id_usuario):
    conexion = get_postgres_connection()

    try:
        with conexion.cursor() as cursor:
            cursor.execute(_SELECT_USUARIO + " WHERE u.id_usuario = %s;", (id_usuario,))
            return cursor.fetchone()

    finally:
        conexion.close()


def email_en_uso(email, excluir_id=None):
    """True si otro usuario ya usa ese email (sin distinguir mayúsculas)."""
    conexion = get_postgres_connection()

    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                SELECT EXISTS (
                    SELECT 1 FROM usuario
                    WHERE lower(email) = lower(%s)
                      AND (%s::bigint IS NULL OR id_usuario <> %s::bigint)
                );
                """,
                (email, excluir_id, excluir_id)
            )
            return cursor.fetchone()[0]

    finally:
        conexion.close()


def modificar_usuario(id_usuario, usuario):
    """Modifica los datos del usuario. La contraseña no se toca aquí
    (ver actualizar_contrasena)."""
    _validar(usuario)
    conexion = get_postgres_connection()

    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                UPDATE usuario
                SET id_cliente = %s,
                    id_proveedor = %s,
                    id_operador = %s,
                    id_rol = %s,
                    nombre = %s,
                    apellido = %s,
                    email = %s,
                    estado = %s
                WHERE id_usuario = %s;
                """,
                (
                    usuario.id_cliente,
                    usuario.id_proveedor,
                    usuario.id_operador,
                    usuario.id_rol,
                    usuario.nombre,
                    usuario.apellido,
                    usuario.email,
                    usuario.estado,
                    id_usuario
                )
            )

            modificado = cursor.rowcount > 0

        conexion.commit()
        return modificado

    except errors.UniqueViolation:
        conexion.rollback()
        raise ValueError(EMAIL_REPETIDO) from None

    except Exception:
        conexion.rollback()
        raise

    finally:
        conexion.close()


def datos_para_contrasena(id_usuario):
    """(hash, email, nombre, apellido) o None. Solo para verificar o validar."""
    conexion = get_postgres_connection()

    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                SELECT contrasena_encriptada, email, nombre, apellido
                FROM usuario WHERE id_usuario = %s;
                """,
                (id_usuario,)
            )
            return cursor.fetchone()

    finally:
        conexion.close()


def actualizar_contrasena(id_usuario, contrasena_hash, debe_cambiar):
    """Guarda el hash nuevo, limpia intentos y bloqueo.

    debe_cambiar=True tras un reseteo del administrador: el usuario la cambia
    al entrar.
    """
    conexion = get_postgres_connection()

    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                UPDATE usuario
                SET contrasena_encriptada = %s,
                    debe_cambiar_contrasena = %s,
                    contrasena_actualizada_en = CURRENT_TIMESTAMP,
                    intentos_fallidos = 0,
                    bloqueado_hasta = NULL
                WHERE id_usuario = %s;
                """,
                (contrasena_hash, debe_cambiar, id_usuario)
            )
            modificado = cursor.rowcount > 0

        conexion.commit()
        return modificado

    except Exception:
        conexion.rollback()
        raise

    finally:
        conexion.close()


def desbloquear_usuario(id_usuario):
    """Limpia intentos y bloqueo sin cambiar la contraseña.

    Devuelve False si el usuario no existe o no tenía bloqueo ni intentos.
    """
    conexion = get_postgres_connection()

    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                UPDATE usuario
                SET intentos_fallidos = 0, bloqueado_hasta = NULL
                WHERE id_usuario = %s
                  AND (intentos_fallidos > 0 OR bloqueado_hasta IS NOT NULL);
                """,
                (id_usuario,)
            )
            modificado = cursor.rowcount > 0

        conexion.commit()
        return modificado

    except Exception:
        conexion.rollback()
        raise

    finally:
        conexion.close()


def eliminar_usuario(id_usuario):
    conexion = get_postgres_connection()

    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                DELETE FROM usuario
                WHERE id_usuario = %s;
                """,
                (id_usuario,)
            )

            eliminado = cursor.rowcount > 0

        conexion.commit()
        return eliminado

    except Exception:
        conexion.rollback()
        raise

    finally:
        conexion.close()


def existe_cliente(id_cliente):
    conexion = get_postgres_connection()

    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                SELECT EXISTS(
                    SELECT 1
                    FROM cliente
                    WHERE id_cliente = %s
                );
                """,
                (id_cliente,)
            )

            return cursor.fetchone()[0]

    finally:
        conexion.close()


def existe_rol(id_rol):
    conexion = get_postgres_connection()

    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                SELECT EXISTS(
                    SELECT 1
                    FROM rol
                    WHERE id_rol = %s
                );
                """,
                (id_rol,)
            )

            return cursor.fetchone()[0]

    finally:
        conexion.close()
