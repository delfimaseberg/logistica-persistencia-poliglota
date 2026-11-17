from datetime import datetime, timezone
from getpass import getpass
from zoneinfo import ZoneInfo

from app.repositories.sesion_repository import (
    buscar_usuario_por_email,
    iniciar_sesion_db,
    listar_sesiones_activas,
    listar_usuarios_bloqueados,
    expirar_sesiones_inactivas,
    cerrar_sesion_db,
    cerrar_sesion_ajena_db,
    registrar_intento_fallido,
    registrar_ingreso_correcto
)
from app.utils.logger import obtener_logger
from app.utils.politica_contrasena import INTENTOS_MAXIMOS, MINUTOS_BLOQUEO, MINUTOS_INACTIVIDAD
from app.services.autenticacion import requiere_permiso


ZONA_ARGENTINA = ZoneInfo("America/Argentina/Buenos_Aires")  # para mostrar las fechas

from app.services.autenticacion import (
    establecer_sesion,
    obtener_sesion_actual,
    limpiar_sesion,
    verificar_permiso
)

from app.utils.seguridad import verificar_contrasena
from app.utils.errores import mensaje_error


logger = obtener_logger("sesiones")  # inicios, fallos y bloqueos a logs/app.log


def iniciar_sesion_service():  # pide email y contraseña e inicia la sesión; opción 1 de la pantalla de inicio
    print("\n==========================================")
    print("              INICIAR SESIÓN")
    print("==========================================")

    try:
        if obtener_sesion_actual() is not None:
            print("\nYa existe una sesión iniciada.")
            return True

        email = input("Email: ").strip()
        contrasena = getpass("Contraseña: ")  # oculta, no se ve al escribir

        usuario = buscar_usuario_por_email(email)  # datos, hash y estado de bloqueo desde PostgreSQL

        if usuario is None:
            # No se registra lo tipeado: a veces es la contraseña.
            logger.warning("Inicio de sesión fallido: email no registrado")
            print("\nEmail o contraseña incorrectos.")
            return False

        (
            id_usuario,
            nombre,
            apellido,
            email_usuario,
            hash_guardado,
            estado,
            descripcion_rol,
            nivel_permisos,
            bloqueado,
            minutos_restantes,
            debe_cambiar
        ) = usuario

        if bloqueado:  # bloqueado: no se prueba la contraseña
            logger.warning("Inicio de sesión rechazado: usuario %s bloqueado", id_usuario)
            print("\nDemasiados intentos fallidos. Probá de nuevo en "
                  f"{minutos_restantes} minuto{'s' if minutos_restantes != 1 else ''}.")
            return False

        if not verificar_contrasena(contrasena, hash_guardado):  # contraseña mal: suma un intento fallido
            intentos, bloqueado_ahora = registrar_intento_fallido(id_usuario)  # al quinto seguido queda bloqueado 15 minutos
            logger.warning("Inicio de sesión fallido: usuario %s (intento %s de %s)",
                           id_usuario, intentos, INTENTOS_MAXIMOS)
            if bloqueado_ahora:
                logger.warning("Usuario %s bloqueado por %s minutos", id_usuario, MINUTOS_BLOQUEO)
                print(f"\nDemasiados intentos fallidos. El usuario quedó bloqueado por "
                      f"{MINUTOS_BLOQUEO} minutos.")
            else:
                print("\nEmail o contraseña incorrectos.")
            return False

        # Solo quien conoce la contraseña sabe que el usuario existe y está inactivo.
        if estado != "ACTIVO":
            print("\nEl usuario está inactivo.")
            return False

        registrar_ingreso_correcto(id_usuario)  # entró bien: los intentos vuelven a cero

        id_sesion = iniciar_sesion_db(id_usuario)  # nueva sesión ACTIVA en PostgreSQL

        if id_sesion is None:
            print("\nNo se pudo registrar la sesión.")
            return False

        establecer_sesion(id_sesion, id_usuario)
        logger.info("Inicio de sesión: usuario %s", id_usuario)

        if debe_cambiar:  # después de un restablecimiento tiene que elegir otra contraseña
            from app.services.contrasena_service import cambio_obligatorio
            if not cambio_obligatorio(id_usuario, id_sesion, email_usuario, nombre, apellido):
                cerrar_sesion_db(id_sesion, id_usuario)
                limpiar_sesion()
                print("\nSin una contraseña nueva no se puede continuar. Sesión cerrada.")
                return False

        print("\nSesión iniciada correctamente.")
        print(f"Bienvenido/a, {nombre} {apellido}.")
        print(f"Rol: {descripcion_rol}")
        print(f"Nivel de permisos: {nivel_permisos}")

        return True

    except Exception as error:
        print(f"\nError al iniciar sesión: {mensaje_error(error)}")
        return False


def cerrar_sesion_service():  # cierra la propia sesión; opción Cerrar sesión o Salir de los menús
    print("\n--- CERRAR SESIÓN ---")

    try:
        usuario = obtener_sesion_actual()

        if usuario is None:
            limpiar_sesion()
            print("\nNo hay una sesión activa.")
            return True

        cerrada = cerrar_sesion_db(  # la sesión pasa a CERRADA en PostgreSQL
            usuario["id_sesion"],
            usuario["id_usuario"]
        )

        if cerrada:
            limpiar_sesion()
            print("\nSesión cerrada correctamente.")
            return True

        print("\nNo se pudo cerrar la sesión.")
        return False

    except Exception as error:
        print(f"\nError al cerrar sesión: {mensaje_error(error)}")
        return False


@requiere_permiso(5)
def consultar_sesiones_activas_service():  # sesiones abiertas y usuarios bloqueados; opción 7 del menú de usuarios
    if not verificar_permiso(5):
        input("\nPresioná Enter para continuar...")
        return

    print("\n--- SESIONES ACTIVAS ---")

    try:
        vencidas = expirar_sesiones_inactivas()  # antes de listar, cierra las que superaron los 30 minutos
        if vencidas:
            logger.info("Sesiones cerradas por inactividad: %s", vencidas)
        sesiones = listar_sesiones_activas()
        propia = obtener_sesion_actual()

        mostrar_usuarios_bloqueados()

        if vencidas:
            print(f"\nSe cerraron {vencidas} sesión(es) por inactividad "
                  f"(más de {MINUTOS_INACTIVIDAD} minutos sin uso).")

        if not sesiones:
            print("\nNo hay sesiones activas.")
            return

        print(f"\nTotal de sesiones activas: {len(sesiones)}")
        ahora = datetime.now(timezone.utc)

        for numero, sesion in enumerate(sesiones, 1):
            marca = " (tu sesión)" if propia and sesion[0] == propia["id_sesion"] else ""
            print("----------------------------")
            print(f"{numero}. {sesion[2]} {sesion[3]} | {sesion[4]}{marca}")
            print(f"   Pertenece a: {sesion[6]}")
            print(f"   Inicio: {formatear_fecha(sesion[5])} | "
                  f"duración: {formatear_duracion(ahora - sesion[5])}")
            if len(sesion) > 7 and sesion[7] is not None:
                print(f"   Última actividad: {formatear_fecha(sesion[7])}")

        cerrar_sesion_de_otro(sesiones, propia)

    except Exception as error:
        print(f"\nError al consultar sesiones: {mensaje_error(error)}")

    finally:
        input("\nPresioná Enter para continuar...")


def mostrar_usuarios_bloqueados():  # lista los bloqueos vigentes; la usa consultar_sesiones_activas_service
    bloqueados = listar_usuarios_bloqueados()
    if not bloqueados:
        print("\nNo hay usuarios bloqueados.")
        return
    print(f"\nUsuarios bloqueados por intentos fallidos: {len(bloqueados)}")
    for b in bloqueados:
        print(f"  {b[1]} {b[2]} | {b[3]} | bloqueado hasta {formatear_fecha(b[4])}")
    print("  (Gestión de usuarios > 'Desbloquear usuario' quita el bloqueo.)")


def formatear_fecha(fecha):  # fecha en hora argentina
    return fecha.astimezone(ZONA_ARGENTINA).strftime("%d/%m/%Y %H:%M")


def formatear_duracion(delta):  # duración en días, horas y minutos
    minutos = int(delta.total_seconds() // 60)
    dias, minutos = divmod(minutos, 1440)
    horas, minutos = divmod(minutos, 60)
    if dias:
        return f"{dias} d {horas} h"
    return f"{horas} h {minutos} min"


def cerrar_sesion_de_otro(sesiones, propia):  # el administrador cierra la sesión de otro usuario; la usa consultar_sesiones_activas_service
    """Baja del ABM de sesiones: el administrador cierra una sesión ajena."""
    valor = input("\nNúmero de sesión a cerrar (Enter = ninguna): ").strip()
    if not valor:
        return False
    if not valor.isdigit() or not 1 <= int(valor) <= len(sesiones):
        print("Número inválido.")
        return False

    sesion = sesiones[int(valor) - 1]
    if propia and sesion[1] == propia["id_usuario"]:  # la propia se cierra con Cerrar sesión
        print("Para cerrar tu propia sesión usá la opción 'Cerrar sesión'.")
        return False

    confirmar = input(
        f"¿Cerrar la sesión de {sesion[2]} {sesion[3]}? (S/N): "
    ).strip().upper()
    if confirmar != "S":
        print("Cancelado.")
        return False

    if cerrar_sesion_ajena_db(sesion[0], propia["id_usuario"]):  # queda registrado quién la cerró
        print("Sesión cerrada. El usuario deberá volver a iniciar sesión.")
        return True

    print("La sesión ya no estaba activa.")
    return False