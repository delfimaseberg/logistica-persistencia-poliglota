from app.database.postgres_connection import get_postgres_connection


def crear_rol(rol):
    conexion = get_postgres_connection()

    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO rol (descripcion, nivel_permisos)
                VALUES (%s, %s)
                RETURNING id_rol;
                """,
                (
                    rol.descripcion,
                    rol.nivel_permisos
                )
            )

            id_rol = cursor.fetchone()[0]

        conexion.commit()
        return id_rol

    except Exception:
        conexion.rollback()
        raise

    finally:
        conexion.close()


def listar_roles():
    conexion = get_postgres_connection()

    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    id_rol,
                    descripcion,
                    nivel_permisos
                FROM rol
                ORDER BY id_rol;
                """
            )

            return cursor.fetchall()

    finally:
        conexion.close()


def buscar_rol_por_id(id_rol):
    conexion = get_postgres_connection()

    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    id_rol,
                    descripcion,
                    nivel_permisos
                FROM rol
                WHERE id_rol = %s;
                """,
                (id_rol,)
            )

            return cursor.fetchone()

    finally:
        conexion.close()


def modificar_rol(id_rol, rol):
    conexion = get_postgres_connection()

    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                UPDATE rol
                SET descripcion = %s,
                    nivel_permisos = %s
                WHERE id_rol = %s;
                """,
                (
                    rol.descripcion,
                    rol.nivel_permisos,
                    id_rol
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


def eliminar_rol(id_rol):
    conexion = get_postgres_connection()

    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                DELETE FROM rol
                WHERE id_rol = %s;
                """,
                (id_rol,)
            )

            eliminado = cursor.rowcount > 0

        conexion.commit()
        return eliminado

    except Exception:
        conexion.rollback()
        raise

    finally:
        conexion.close()