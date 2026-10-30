from functools import wraps

from app.database.postgres_connection import get_postgres_connection


_sesion_actual = None


def establecer_sesion(id_sesion, id_usuario):
    global _sesion_actual

    _sesion_actual = {
        "id_sesion": id_sesion,
        "id_usuario": id_usuario
    }


def limpiar_sesion():
    global _sesion_actual
    _sesion_actual = None


def obtener_sesion_actual():
    global _sesion_actual

    if _sesion_actual is None:
        return None

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
                    r.descripcion,
                    r.nivel_permisos,
                    u.id_cliente,
                    u.id_proveedor,
                    u.id_operador
                FROM sesion s
                JOIN usuario u
                    ON s.id_usuario = u.id_usuario
                JOIN rol r
                    ON u.id_rol = r.id_rol
                WHERE s.id_sesion = %s
                  AND s.id_usuario = %s
                  AND s.estado = 'ACTIVA'
                  AND s.fecha_fin IS NULL
                  AND u.estado = 'ACTIVO';
                """,
                (
                    _sesion_actual["id_sesion"],
                    _sesion_actual["id_usuario"]
                )
            )

            resultado = cursor.fetchone()

    if resultado is None:
        limpiar_sesion()
        return None

    return {
        "id_sesion": resultado[0],
        "id_usuario": resultado[1],
        "nombre": resultado[2],
        "apellido": resultado[3],
        "email": resultado[4],
        "rol": resultado[5],
        "nivel_permisos": resultado[6],
        # Parte a la que pertenece el usuario. Como mucho una no es None;
        # las tres en None = usuario interno.
        "id_cliente": resultado[7],
        "id_proveedor": resultado[8],
        "id_operador": resultado[9]
    }


def parte_de(sesion):
    """('INTERNO', None), ('CLIENTE', id), ('OPERADOR', id) o ('PROVEEDOR', id)."""
    if sesion is None:
        return None, None
    if sesion.get("id_cliente") is not None:
        return "CLIENTE", sesion["id_cliente"]
    if sesion.get("id_operador") is not None:
        return "OPERADOR", sesion["id_operador"]
    if sesion.get("id_proveedor") is not None:
        return "PROVEEDOR", sesion["id_proveedor"]
    return "INTERNO", None


def es_interno(sesion):
    return parte_de(sesion)[0] == "INTERNO"


def solo_internos(funcion):
    """Decorador para operaciones que solo hace la empresa (emitir, cobrar,
    pagar, cerrar, ABM). Segunda barrera además del menú."""
    @wraps(funcion)
    def envoltura(*args, **kwargs):
        sesion = obtener_sesion_actual()
        if sesion is None or not es_interno(sesion):
            print("\nOperación disponible solo para usuarios internos.")
            return None
        return funcion(*args, **kwargs)
    return envoltura


def verificar_sesion():
    """Hay una sesión activa (cualquier parte). Para pantallas del portal."""
    if obtener_sesion_actual() is None:
        print("\nDebe iniciar sesión para continuar.")
        return False
    return True


def verificar_permiso(nivel_minimo):
    """Acceso a las funciones INTERNAS de la empresa.

    Los usuarios de clientes, operadores y proveedores no acceden a ninguna,
    sin importar su nivel: usan su portal, que filtra por su parte.
    """
    usuario = obtener_sesion_actual()

    if usuario is None:
        print("\nDebe iniciar sesión para continuar.")
        return False

    if not es_interno(usuario):
        print("\nOpción no disponible para usuarios de clientes, operadores "
              "o proveedores.")
        return False

    if usuario["nivel_permisos"] < nivel_minimo:
        print("\nAcceso denegado: permisos insuficientes.")
        print(f"Nivel requerido: {nivel_minimo}")
        print(f"Su nivel: {usuario['nivel_permisos']}")
        return False

    return True