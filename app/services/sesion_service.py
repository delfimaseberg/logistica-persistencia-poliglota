from datetime import datetime, timezone
from getpass import getpass
from zoneinfo import ZoneInfo

from app.repositories.sesion_repository import (
    buscar_usuario_por_email,
    iniciar_sesion_db,
    listar_sesiones_activas,
    cerrar_sesion_db,
    cerrar_sesion_ajena_db
)


ZONA_ARGENTINA = ZoneInfo("America/Argentina/Buenos_Aires")

from app.services.autenticacion import (
    establecer_sesion,
    obtener_sesion_actual,
    limpiar_sesion,
    verificar_permiso
)

from app.utils.seguridad import verificar_contrasena


def iniciar_sesion_service():
    print("\n==========================================")
    print("              INICIAR SESIÓN")
    print("==========================================")

    try:
        if obtener_sesion_actual() is not None:
            print("\nYa existe una sesión iniciada.")
            return True

        email = input("Email: ").strip()
        contrasena = getpass("Contraseña: ")

        usuario = buscar_usuario_por_email(email)

        if usuario is None:
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
            nivel_permisos
        ) = usuario

        if estado != "ACTIVO":
            print("\nEl usuario está inactivo.")
            return False

        if not verificar_contrasena(contrasena, hash_guardado):
            print("\nEmail o contraseña incorrectos.")
            return False

        id_sesion = iniciar_sesion_db(id_usuario)

        if id_sesion is None:
            print("\nNo se pudo registrar la sesión.")
            return False

        establecer_sesion(id_sesion, id_usuario)

        print("\nSesión iniciada correctamente.")
        print(f"Bienvenido/a, {nombre} {apellido}.")
        print(f"Rol: {descripcion_rol}")
        print(f"Nivel de permisos: {nivel_permisos}")

        return True

    except Exception as error:
        print(f"\nError al iniciar sesión: {error}")
        return False


def cerrar_sesion_service():
    print("\n--- CERRAR SESIÓN ---")

    try:
        usuario = obtener_sesion_actual()

        if usuario is None:
            limpiar_sesion()
            print("\nNo hay una sesión activa.")
            return True

        cerrada = cerrar_sesion_db(
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
        print(f"\nError al cerrar sesión: {error}")
        return False


def consultar_sesiones_activas_service():
    if not verificar_permiso(5):
        input("\nPresione Enter para continuar...")
        return

    print("\n--- SESIONES ACTIVAS ---")

    try:
        sesiones = listar_sesiones_activas()
        propia = obtener_sesion_actual()

        if not sesiones:
            print("\nNo hay sesiones activas.")
            return

        print(f"\nTotal de sesiones activas: {len(sesiones)}")
        ahora = datetime.now(timezone.utc)

        for numero, sesion in enumerate(sesiones, 1):
            marca = " (su sesión)" if propia and sesion[0] == propia["id_sesion"] else ""
            print("----------------------------")
            print(f"{numero}. {sesion[2]} {sesion[3]} | {sesion[4]}{marca}")
            print(f"   Pertenece a: {sesion[6]}")
            print(f"   Inicio: {formatear_fecha(sesion[5])} | "
                  f"duración: {formatear_duracion(ahora - sesion[5])}")

        cerrar_sesion_de_otro(sesiones, propia)

    except Exception as error:
        print(f"\nError al consultar sesiones: {error}")

    finally:
        input("\nPresione Enter para continuar...")


def formatear_fecha(fecha):
    return fecha.astimezone(ZONA_ARGENTINA).strftime("%d/%m/%Y %H:%M")


def formatear_duracion(delta):
    minutos = int(delta.total_seconds() // 60)
    dias, minutos = divmod(minutos, 1440)
    horas, minutos = divmod(minutos, 60)
    if dias:
        return f"{dias} d {horas} h"
    return f"{horas} h {minutos} min"


def cerrar_sesion_de_otro(sesiones, propia):
    """Baja del ABM de sesiones: el administrador cierra una sesión ajena."""
    valor = input("\nNúmero de sesión a cerrar (Enter = ninguna): ").strip()
    if not valor:
        return False
    if not valor.isdigit() or not 1 <= int(valor) <= len(sesiones):
        print("Número inválido.")
        return False

    sesion = sesiones[int(valor) - 1]
    if propia and sesion[1] == propia["id_usuario"]:
        print("Para cerrar su propia sesión use la opción 'Cerrar sesión'.")
        return False

    confirmar = input(
        f"¿Cerrar la sesión de {sesion[2]} {sesion[3]}? (S/N): "
    ).strip().upper()
    if confirmar != "S":
        print("Cancelado.")
        return False

    if cerrar_sesion_ajena_db(sesion[0], propia["id_usuario"]):
        print("Sesión cerrada. El usuario deberá volver a iniciar sesión.")
        return True

    print("La sesión ya no estaba activa.")
    return False