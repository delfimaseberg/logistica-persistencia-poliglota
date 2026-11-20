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

from app.services.contrasena_service import (
    restablecer_contrasena_service,
    desbloquear_usuario_service
)

from app.services.autenticacion import verificar_permiso

from app.ui.menu_roles import mostrar_menu_roles


def ejecutar_operacion(funcion, nivel_minimo):  # ejecuta la opción si el nivel alcanza
    if verificar_permiso(nivel_minimo):
        funcion()


def mostrar_menu_usuarios():  # menú de usuarios; opción 2 del menú principal (nivel 3)
    if not verificar_permiso(3):
        return

    while True:
        if not verificar_permiso(3):  # se controla en cada vuelta por si venció la sesión
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
        print("7. Sesiones activas y usuarios bloqueados")
        print("8. Restablecer contraseña de un usuario")
        print("9. Desbloquear usuario")
        print("0. Volver al menú principal")

        opcion = input("\nSeleccioná una opción: ").strip()

        if opcion == "1":
            ejecutar_operacion(registrar_usuario, 5)  # consultar pide nivel 3; dar de alta, modificar o borrar, nivel 5

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

        elif opcion == "7":  # sesiones abiertas y usuarios bloqueados
            ejecutar_operacion(
                consultar_sesiones_activas_service,
                5
            )

        elif opcion == "8":  # contraseña temporal que el usuario cambia al entrar
            ejecutar_operacion(restablecer_contrasena_service, 5)

        elif opcion == "9":  # quita el bloqueo sin cambiar la contraseña
            ejecutar_operacion(desbloquear_usuario_service, 5)

        elif opcion == "0":
            break

        else:
            print("\nOpción inválida.")