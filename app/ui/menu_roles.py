from app.services.rol_service import (
    registrar_rol,
    listar_roles_service,
    buscar_rol_service,
    modificar_rol_service,
    eliminar_rol_service
)

from app.services.autenticacion import verificar_permiso


def mostrar_menu_roles():
    if not verificar_permiso(5):
        return

    while True:
        if not verificar_permiso(5):
            return

        print("\n==========================================")
        print("            GESTIÓN DE ROLES")
        print("==========================================")
        print("1. Registrar rol")
        print("2. Listar roles")
        print("3. Buscar rol")
        print("4. Modificar rol")
        print("5. Eliminar rol")
        print("0. Volver a gestión de usuarios")

        opcion = input("\nSeleccioná una opción: ").strip()

        if opcion == "1":
            registrar_rol()

        elif opcion == "2":
            listar_roles_service()

        elif opcion == "3":
            buscar_rol_service()

        elif opcion == "4":
            modificar_rol_service()

        elif opcion == "5":
            eliminar_rol_service()

        elif opcion == "0":
            break

        else:
            print("\nOpción inválida. Intentá nuevamente.")