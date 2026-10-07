from app.database.postgres_connection import get_postgres_connection


def crear_usuario(usuario):
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
                        estado
                    )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id_usuario;
                """,
                (
                    usuario.id_cliente,
                    usuario.id_rol,
                    usuario.nombre,
                    usuario.apellido,
                    usuario.email,
                    usuario.contrasena_encriptada,
                    usuario.estado
                )
            )

            id_usuario = cursor.fetchone()[0]

        conexion.commit()
        return id_usuario

    except Exception:
        conexion.rollback()
        raise

    finally:
        conexion.close()


def listar_usuarios():
    conexion = get_postgres_connection()

    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    id_usuario,
                    id_cliente,
                    id_rol,
                    nombre,
                    apellido,
                    email,
                    estado,
                    fecha_registro
                FROM usuario
                ORDER BY id_usuario;
                """
            )

            return cursor.fetchall()

    finally:
        conexion.close()


def buscar_usuario_por_id(id_usuario):
    conexion = get_postgres_connection()

    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    id_usuario,
                    id_cliente,
                    id_rol,
                    nombre,
                    apellido,
                    email,
                    estado,
                    fecha_registro
                FROM usuario
                WHERE id_usuario = %s;
                """,
                (id_usuario,)
            )

            return cursor.fetchone()

    finally:
        conexion.close()


def modificar_usuario(id_usuario, usuario):
    conexion = get_postgres_connection()

    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                UPDATE usuario
                SET id_cliente = %s,
                    id_rol = %s,
                    nombre = %s,
                    apellido = %s,
                    email = %s,
                    contrasena_encriptada = %s,
                    estado = %s
                WHERE id_usuario = %s;
                """,
                (
                    usuario.id_cliente,
                    usuario.id_rol,
                    usuario.nombre,
                    usuario.apellido,
                    usuario.email,
                    usuario.contrasena_encriptada,
                    usuario.estado,
                    id_usuario
                )
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