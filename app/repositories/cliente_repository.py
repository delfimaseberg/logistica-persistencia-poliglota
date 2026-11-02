from psycopg import errors

from app.database.postgres_connection import get_postgres_connection
from app.utils.validaciones_datos import validar_contacto
from app.utils import formato


def _validar(cliente):
    """CUIT con dígito verificador si es de Argentina; si no, formato. Largos,
    email y teléfono según las columnas de la base."""
    datos = validar_contacto(vars(cliente), cuit_por_pais=True, direccion_obligatoria=True)
    for campo in ("razon_social", "cuit", "email", "telefono", "direccion", "pais"):
        setattr(cliente, campo, datos[campo])
    if cliente.estado not in ("ACTIVO", "INACTIVO"):
        raise ValueError("El estado del cliente debe ser ACTIVO o INACTIVO.")


def _repetido(error):
    restriccion = getattr(getattr(error, "diag", None), "constraint_name", "") or ""
    if "email" in restriccion:
        return ValueError("Ya existe un cliente con ese email.")
    return ValueError("Ya existe un cliente con esa identificación fiscal.")


def dato_en_uso(campo, valor, excluir_id=None):
    """True si otro cliente usa ese CUIT o email (el email sin distinguir mayúsculas)."""
    columna = {"cuit": "cuit", "email": "lower(email)"}[campo]
    parametro = valor if campo == "cuit" else str(valor).lower()
    conexion = get_postgres_connection()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT EXISTS (
                    SELECT 1 FROM cliente
                    WHERE {columna} = %s
                      AND (%s::bigint IS NULL OR id_cliente <> %s::bigint)
                );
                """,
                (parametro, excluir_id, excluir_id)
            )
            return cursor.fetchone()[0]
    finally:
        conexion.close()


def crear_cliente(cliente):
    _validar(cliente)
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

    except errors.UniqueViolation as error:
        conexion.rollback()
        raise _repetido(error) from None

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
    _validar(cliente)
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

    except errors.UniqueViolation as error:
        conexion.rollback()
        raise _repetido(error) from None

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