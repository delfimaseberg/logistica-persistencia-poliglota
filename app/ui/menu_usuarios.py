from app.services.usuario_service import (
    registrar_usuario,
    listar_usuarios_service,
    buscar_usuario_service,
    modificar_usuario_service,
    eliminar_usuario_service
)

from app.services.sesion_service import (
    consultar_sesiones_activas_service
)

from app.services.autenticacion import verificar_permiso

from app.ui.menu_roles import mostrar_menu_roles


def ejecutar_operacion(funcion, nivel_minimo):
    if verificar_permiso(nivel_minimo):
        funcion()


def mostrar_menu_usuarios():
    if not verificar_permiso(3):
        return

    while True:
        if not verificar_permiso(3):
            return

        print("\n==========================================")
        print("          GESTIÓN DE USUARIOS")
        print("==========================================")
        print("1. Registrar usuario")
        print("2. Listar usuarios")
        print("3. Buscar usuario")
        print("4. Modificar usuario")
        print("5. Eliminar usuario")
        print("6. Gestión de roles")
        print("7. Sesiones activas (consultar y cerrar)")
        print("0. Volver al menú principal")

        opcion = input("\nSeleccione una opción: ").strip()

        if opcion == "1":
            ejecutar_operacion(registrar_usuario, 5)

        elif opcion == "2":
            ejecutar_operacion(listar_usuarios_service, 3)

        elif opcion == "3":
            ejecutar_operacion(buscar_usuario_service, 3)

        elif opcion == "4":
            ejecutar_operacion(modificar_usuario_service, 5)

        elif opcion == "5":
            ejecutar_operacion(eliminar_usuario_service, 5)

        elif opcion == "6":
            ejecutar_operacion(mostrar_menu_roles, 5)

        elif opcion == "7":
            ejecutar_operacion(
                consultar_sesiones_activas_service,
                5
            )

        elif opcion == "0":
            break

        else:
            print("\nOpción inválida.")