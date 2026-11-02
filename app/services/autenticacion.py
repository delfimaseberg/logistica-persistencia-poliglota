from functools import wraps

from app.database.postgres_connection import get_postgres_connection
from app.utils.logger import obtener_logger
from app.utils.politica_contrasena import (
    MINUTOS_INACTIVIDAD,
    SEGUNDOS_ENTRE_REGISTROS_DE_ACTIVIDAD,
)


logger = obtener_logger("autenticacion")

AVISOS_CIERRE = {
    "ADMINISTRADOR": "Tu sesión fue cerrada por un administrador.",
    "INACTIVIDAD": f"Tu sesión se cerró por inactividad ({MINUTOS_INACTIVIDAD} minutos).",
}

_sesion_actual = None
# Aviso para el usuario cuya sesión cerró un administrador.
_aviso_cierre = None


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
                    u.id_operador,
                    (now() - s.ultima_actividad) > make_interval(mins => %s) AS expirada,
                    (now() - s.ultima_actividad) > make_interval(secs => %s) AS registrar
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
                    MINUTOS_INACTIVIDAD,
                    SEGUNDOS_ENTRE_REGISTROS_DE_ACTIVIDAD,
                    _sesion_actual["id_sesion"],
                    _sesion_actual["id_usuario"]
                )
            )

            resultado = cursor.fetchone()

            if resultado is not None and resultado[10]:
                # Sin actividad durante el plazo: la sesión vence.
                cursor.execute(
                    """
                    UPDATE sesion
                    SET estado = 'EXPIRADA',
                        fecha_fin = GREATEST(
                            fecha_inicio,
                            LEAST(now(), ultima_actividad + make_interval(mins => %s)))
                    WHERE id_sesion = %s AND estado = 'ACTIVA' AND fecha_fin IS NULL;
                    """,
                    (MINUTOS_INACTIVIDAD, _sesion_actual["id_sesion"])
                )
                logger.info("Sesión %s del usuario %s cerrada por inactividad",
                            _sesion_actual["id_sesion"], _sesion_actual["id_usuario"])
                resultado = None
                motivo = "INACTIVIDAD"
            elif resultado is not None and resultado[11]:
                cursor.execute(
                    "UPDATE sesion SET ultima_actividad = now() WHERE id_sesion = %s;",
                    (_sesion_actual["id_sesion"],)
                )
                motivo = None
            else:
                motivo = None

    if resultado is None:
        global _aviso_cierre
        try:
            if motivo is None:
                from app.repositories.sesion_repository import motivo_cierre
                motivo = motivo_cierre(_sesion_actual["id_sesion"])
        except Exception:
            pass
        if motivo in AVISOS_CIERRE:
            _aviso_cierre = AVISOS_CIERRE[motivo]
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


def tomar_aviso_cierre():
    """Devuelve el aviso pendiente (una sola vez) o None."""
    global _aviso_cierre
    aviso, _aviso_cierre = _aviso_cierre, None
    return aviso


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


def requiere_permiso(nivel_minimo, portal=(), portal_con_dato=False, lanzar=False):
    """Decorador: el servicio verifica el permiso por sí mismo, no solo el menú.

    nivel_minimo: nivel interno requerido (como en el menú que lo llama).
    portal: partes externas que también pueden usarlo porque la función ya
        filtra por su parte (por ejemplo, el portal del cliente).
    portal_con_dato: la parte externa solo entra si la llamada trae el dato ya
        verificado como propio (por ejemplo, la fila del envío del cliente).
    lanzar: para funciones de lógica (no pantallas): en vez de avisar y
        devolver None, lanza PermissionError.
    """
    def decorador(funcion):
        @wraps(funcion)
        def envoltura(*args, **kwargs):
            sesion = obtener_sesion_actual()
            tipo = parte_de(sesion)[0]
            if sesion is not None and tipo in portal:
                if not portal_con_dato or args or any(v is not None for v in kwargs.values()):
                    return funcion(*args, **kwargs)
                logger.warning("Acceso denegado a %s: usuario %s (%s) sin dato propio",
                               funcion.__name__, sesion["id_usuario"], tipo)
                if lanzar:
                    raise PermissionError("Opción no disponible para tu usuario.")
                print("\nOpción no disponible para tu usuario.")
                return None
            permitido = (
                sesion is not None and es_interno(sesion)
                and sesion["nivel_permisos"] >= nivel_minimo
            ) if lanzar else verificar_permiso(nivel_minimo)
            if not permitido:
                if sesion is not None:
                    logger.warning("Acceso denegado a %s: usuario %s, nivel requerido %s",
                                   funcion.__name__, sesion["id_usuario"], nivel_minimo)
                if lanzar:
                    raise PermissionError("No tenés permisos para esta operación.")
                return None
            return funcion(*args, **kwargs)
        envoltura.nivel_requerido = nivel_minimo
        envoltura.partes_portal = tuple(portal)
        return envoltura
    return decorador


def verificar_sesion():
    """Hay una sesión activa (cualquier parte). Para pantallas del portal."""
    if obtener_sesion_actual() is None:
        print("\n" + (tomar_aviso_cierre() or "Debés iniciar sesión para continuar."))
        return False
    return True


def verificar_permiso(nivel_minimo):
    """Acceso a las funciones INTERNAS de la empresa.

    Los usuarios de clientes, operadores y proveedores no acceden a ninguna,
    sin importar su nivel: usan su portal, que filtra por su parte.
    """
    usuario = obtener_sesion_actual()

    if usuario is None:
        print("\n" + (tomar_aviso_cierre() or "Debés iniciar sesión para continuar."))
        return False

    if not es_interno(usuario):
        print("\nOpción no disponible para usuarios de clientes, operadores "
              "o proveedores.")
        return False

    if usuario["nivel_permisos"] < nivel_minimo:
        print("\nAcceso denegado: permisos insuficientes.")
        print(f"Nivel requerido: {nivel_minimo}")
        print(f"Tu nivel: {usuario['nivel_permisos']}")
        return False

    return True