from app.database.postgres_connection import get_postgres_connection


def crear_cliente(cliente):
    conexion = get_postgres_connection()

    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO cliente
                    (razon_social, cuit, email, telefono, direccion, pais, estado)
                VALUES
                    (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id_cliente;
                """,
                (
                    cliente.razon_social,
                    cliente.cuit,
                    cliente.email,
                    cliente.telefono,
                    cliente.direccion,
                    cliente.pais,
                    cliente.estado
                )
            )

            id_cliente = cursor.fetchone()[0]

        conexion.commit()
        return id_cliente

    except Exception:
        conexion.rollback()
        raise

    finally:
        conexion.close()


def listar_clientes():
    conexion = get_postgres_connection()

    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    id_cliente,
                    razon_social,
                    cuit,
                    email,
                    telefono,
                    direccion,
                    pais,
                    estado
                FROM cliente
                ORDER BY id_cliente;
                """
            )

            return cursor.fetchall()

    finally:
        conexion.close()


def buscar_cliente_por_id(id_cliente):
    conexion = get_postgres_connection()

    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    id_cliente,
                    razon_social,
                    cuit,
                    email,
                    telefono,
                    direccion,
                    pais,
                    estado
                FROM cliente
                WHERE id_cliente = %s;
                """,
                (id_cliente,)
            )

            return cursor.fetchone()

    finally:
        conexion.close()


def modificar_cliente(id_cliente, cliente):
    conexion = get_postgres_connection()

    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                UPDATE cliente
                SET razon_social = %s,
                    cuit = %s,
                    email = %s,
                    telefono = %s,
                    direccion = %s,
                    pais = %s,
                    estado = %s
                WHERE id_cliente = %s;
                """,
                (
                    cliente.razon_social,
                    cliente.cuit,
                    cliente.email,
                    cliente.telefono,
                    cliente.direccion,
                    cliente.pais,
                    cliente.estado,
                    id_cliente
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


def eliminar_cliente(id_cliente):
    conexion = get_postgres_connection()

    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                DELETE FROM cliente
                WHERE id_cliente = %s;
                """,
                (id_cliente,)
            )

            eliminado = cursor.rowcount > 0

        conexion.commit()
        return eliminado

    except Exception:
        conexion.rollback()
        raise

    finally:
        conexion.close()