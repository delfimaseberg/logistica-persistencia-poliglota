from getpass import getpass

from app.repositories.sesion_repository import (
    buscar_usuario_por_email,
    iniciar_sesion_db,
    listar_sesiones_activas,
    cerrar_sesion_db
)

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

        if not sesiones:
            print("\nNo hay sesiones activas.")
        else:
            print(f"\nTotal de sesiones activas: {len(sesiones)}")

            for sesion in sesiones:
                print("----------------------------")
                print(f"ID sesión: {sesion[0]}")
                print(f"ID usuario: {sesion[1]}")
                print(f"Usuario: {sesion[2]} {sesion[3]}")
                print(f"Email: {sesion[4]}")
                print(f"Fecha de inicio: {sesion[5]}")

    except Exception as error:
        print(f"\nError al consultar sesiones: {error}")

    finally:
        input("\nPresione Enter para continuar...")