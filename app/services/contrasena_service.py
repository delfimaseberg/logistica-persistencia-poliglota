"""Cambio, restablecimiento y desbloqueo de contraseñas.

Las contraseñas se piden siempre ocultas (getpass), nunca se muestran ni se
registran en el log: el log guarda solo el id del usuario y lo que pasó.
"""

from getpass import getpass

from app.repositories import sesion_repository, usuario_repository
from app.services.autenticacion import (
    limpiar_sesion,
    obtener_sesion_actual,
    requiere_permiso,
    verificar_sesion,
)
from app.utils import formato
from app.utils.errores import mensaje_error
from app.utils.logger import obtener_logger
from app.utils.politica_contrasena import (
    MINUTOS_BLOQUEO,
    descripcion_politica,
    errores_politica,
)
from app.utils.seguridad import generar_hash_contrasena, verificar_contrasena


logger = obtener_logger("contrasenas")  # solo el id del usuario, nunca la contraseña


def pausar():
    input("\nPresioná Enter para continuar...")


def pedir_contrasena_nueva(email, nombre, apellido, hash_actual=None, titulo="Nueva contraseña"):  # pide una contraseña que cumpla la política; la usan alta de usuario, cambio y restablecimiento
    """Pide la contraseña dos veces (oculta) hasta que cumpla la política.

    Devuelve el texto (para convertirlo en hash enseguida) o None si se
    cancela con Enter.
    """
    print(f"\n{descripcion_politica()}")
    while True:
        contrasena = getpass(f"{titulo} (Enter para cancelar): ")
        if not contrasena:
            return None
        errores = errores_politica(contrasena, email, nombre, apellido)  # controla la política de contraseñas
        if hash_actual and verificar_contrasena(contrasena, hash_actual):  # no puede repetir la actual
            errores.append("ser distinta de la actual")
        if errores:
            print("La contraseña debe " + "; ".join(errores) + ".")
            continue
        if getpass("Repetí la contraseña: ") != contrasena:  # se pide dos veces
            print("Las contraseñas no coinciden. Probá de nuevo.")
            continue
        return contrasena


def guardar_contrasena(id_usuario, contrasena, debe_cambiar, cerrada_por, conservar_sesion=None):  # guarda el hash y cierra las otras sesiones; la usan cambio, cambio obligatorio y restablecimiento
    """Guarda el hash y cierra las demás sesiones del usuario."""
    usuario_repository.actualizar_contrasena(  # también limpia intentos y bloqueo
        id_usuario, generar_hash_contrasena(contrasena), debe_cambiar
    )
    sesion_repository.cerrar_sesiones_de_usuario(id_usuario, cerrada_por, conservar_sesion)


def cambiar_mi_contrasena_service():  # el usuario cambia su contraseña; opción 14 del menú interno y opción de los portales
    """El propio usuario (interno o de un portal), pidiendo la contraseña actual."""
    print("\n--- CAMBIAR MI CONTRASEÑA ---")
    if not verificar_sesion():
        pausar()
        return
    sesion = obtener_sesion_actual()
    try:
        hash_actual, email, nombre, apellido = usuario_repository.datos_para_contrasena(
            sesion["id_usuario"]
        )
        actual = getpass("Contraseña actual: ")
        if not verificar_contrasena(actual, hash_actual):  # la actual mal también cuenta como intento fallido
            intentos, bloqueado = sesion_repository.registrar_intento_fallido(sesion["id_usuario"])
            logger.warning("Cambio de contraseña rechazado: usuario %s, contraseña actual "
                           "incorrecta (intento %s)", sesion["id_usuario"], intentos)
            if bloqueado:  # si llegó al máximo, se bloquea y se cierra la sesión
                logger.warning("Usuario %s bloqueado por %s minutos", sesion["id_usuario"], MINUTOS_BLOQUEO)
                sesion_repository.cerrar_sesion_db(sesion["id_sesion"], sesion["id_usuario"])
                limpiar_sesion()
                print(f"\nDemasiados intentos fallidos. El usuario quedó bloqueado por "
                      f"{MINUTOS_BLOQUEO} minutos y la sesión se cerró.")
            else:
                print("\nLa contraseña actual no es correcta.")
            return
        nueva = pedir_contrasena_nueva(email, nombre, apellido, hash_actual)
        if nueva is None:
            print("\nNo se cambió la contraseña.")
            return
        guardar_contrasena(sesion["id_usuario"], nueva, False, sesion["id_usuario"],  # conserva la sesión actual y cierra las demás
                           conservar_sesion=sesion["id_sesion"])
        logger.info("Usuario %s cambió su contraseña", sesion["id_usuario"])
        print("\nContraseña cambiada correctamente. Se cerraron tus otras sesiones abiertas.")
    except Exception as error:
        print(f"\nNo se pudo cambiar la contraseña: {mensaje_error(error)}")
    finally:
        pausar()


def cambio_obligatorio(id_usuario, id_sesion, email, nombre, apellido):  # obliga a elegir contraseña después de un restablecimiento; la usa iniciar_sesion_service
    """Después de un restablecimiento: hay que elegir una contraseña nueva.

    Devuelve True si la cambió; False si canceló (la sesión no se usa).
    """
    print("\nUn administrador restableció tu contraseña. Elegí una nueva para continuar.")
    hash_actual = usuario_repository.datos_para_contrasena(id_usuario)[0]
    nueva = pedir_contrasena_nueva(email, nombre, apellido, hash_actual)
    if nueva is None:
        return False
    guardar_contrasena(id_usuario, nueva, False, id_usuario, conservar_sesion=id_sesion)  # ya no tiene que cambiarla
    logger.info("Usuario %s eligió su contraseña después del restablecimiento", id_usuario)
    print("\nContraseña cambiada correctamente.")
    return True


def _pedir_usuario_ajeno(accion):  # elige otro usuario; la usan restablecer y desbloquear
    from app.services.usuario_service import mostrar_usuario, pedir_id
    sesion = obtener_sesion_actual()
    id_usuario = pedir_id("ID del usuario: ")
    if id_usuario == sesion["id_usuario"]:  # uno mismo usa Cambiar mi contraseña
        print(f"\nPara {accion} tu propia cuenta usá 'Cambiar mi contraseña'.")
        return None
    usuario = usuario_repository.buscar_usuario_por_id(id_usuario)
    if usuario is None:
        print("Usuario no encontrado.")
        return None
    mostrar_usuario(usuario)
    return usuario


@requiere_permiso(5)
def restablecer_contrasena_service():  # el administrador pone una contraseña temporal; opción 8 del menú de usuarios
    """El administrador asigna una contraseña temporal; el usuario la cambia al entrar."""
    print("\n--- RESTABLECER CONTRASEÑA DE UN USUARIO ---")
    try:
        usuario = _pedir_usuario_ajeno("cambiar la contraseña de")
        if usuario is None:
            return
        nueva = pedir_contrasena_nueva(usuario[5], usuario[3], usuario[4],
                                       titulo="Contraseña temporal")
        if nueva is None:
            print("\nNo se restableció la contraseña.")
            return
        administrador = obtener_sesion_actual()["id_usuario"]
        guardar_contrasena(usuario[0], nueva, True, administrador)  # True: la tiene que cambiar al entrar; se cierran sus sesiones
        logger.info("Administrador %s restableció la contraseña del usuario %s",
                    administrador, usuario[0])
        print("\nContraseña restablecida. El usuario deberá cambiarla en su próximo "
              "inicio de sesión; se cerraron sus sesiones abiertas y se quitó el bloqueo.")
    except Exception as error:
        print(f"\nNo se pudo restablecer la contraseña: {mensaje_error(error)}")
    finally:
        pausar()


@requiere_permiso(5)
def desbloquear_usuario_service():  # quita el bloqueo; opción 9 del menú de usuarios
    """Limpia intentos y bloqueo sin cambiar la contraseña."""
    print("\n--- DESBLOQUEAR USUARIO ---")
    try:
        bloqueados = sesion_repository.listar_usuarios_bloqueados()
        if bloqueados:
            print("Usuarios bloqueados:")
            for b in bloqueados:
                print(f"  {b[0]}. {b[1]} {b[2]} | {b[3]} | hasta {formato.fecha_hora(b[4])}")
        else:
            print("No hay usuarios bloqueados en este momento.")
        usuario = _pedir_usuario_ajeno("desbloquear")
        if usuario is None:
            return
        if input("¿Desbloquear este usuario? (S/N): ").strip().upper() != "S":
            print("Cancelado.")
            return
        administrador = obtener_sesion_actual()["id_usuario"]
        if usuario_repository.desbloquear_usuario(usuario[0]):  # intentos a cero y sin bloqueo
            logger.info("Administrador %s desbloqueó al usuario %s", administrador, usuario[0])
            print("\nUsuario desbloqueado. La contraseña no cambió.")
        else:
            print("\nEl usuario no estaba bloqueado ni tenía intentos fallidos.")
    except Exception as error:
        print(f"\nNo se pudo desbloquear el usuario: {mensaje_error(error)}")
    finally:
        pausar()
