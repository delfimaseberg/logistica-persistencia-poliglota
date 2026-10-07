from app.services.usuario_service import (
    registrar_usuario,
    listar_usuarios_service,
    buscar_usuario_service,
    modificar_usuario_service,
    eliminar_usuario_service
)
from app.ui.menu_roles import mostrar_menu_roles

def mostrar_menu_usuarios():
    while True:
        print("\n==========================================")
        print("          GESTIÓN DE USUARIOS")
        print("==========================================")
        print("1. Registrar usuario")
        print("2. Listar usuarios")
        print("3. Buscar usuario")
        print("4. Modificar usuario")
        print("5. Eliminar usuario")
        print("6. Gestión de roles")
        print("7. Consultar sesiones activas")
        print("0. Volver al menú principal")

        opcion = input("\nSeleccione una opción: ")

        if opcion == "1":
            registrar_usuario()
        elif opcion == "2":
            listar_usuarios_service()
        elif opcion == "3":
            buscar_usuario_service()
        elif opcion == "4":
            modificar_usuario_service()
        elif opcion == "5":
            eliminar_usuario_service()
        elif opcion == "6":
            mostrar_menu_roles()
        elif opcion == "7":
            print("\n>> Sesiones activas")
        elif opcion == "0":
            break
        else:
            print("\nOpción inválida. Intente nuevamente.")