from app.services.rol_service import (
    registrar_rol,
    listar_roles_service,
    buscar_rol_service,
    modificar_rol_service,
    eliminar_rol_service
)


def mostrar_menu_roles():
    while True:
        print("\n==========================================")
        print("            GESTIÓN DE ROLES")
        print("==========================================")
        print("1. Registrar rol")
        print("2. Listar roles")
        print("3. Buscar rol")
        print("4. Modificar rol")
        print("5. Eliminar rol")
        print("0. Volver a gestión de usuarios")

        opcion = input("\nSeleccione una opción: ")

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
            print("\nOpción inválida. Intente nuevamente.")