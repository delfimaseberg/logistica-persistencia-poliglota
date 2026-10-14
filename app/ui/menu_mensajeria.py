from app.services.autenticacion import verificar_permiso

from app.services.mensajeria_service import (
    listar_usuarios_mensajeria_service,
    enviar_mensaje_service,
    consultar_bandeja_service,
    consultar_enviados_service,
    consultar_conversacion_service,
    marcar_leido_service,
    crear_grupo_service,
    listar_grupos_service,
    agregar_miembro_service,
    enviar_mensaje_grupo_service,
    consultar_mensajes_grupo_service
)


def mostrar_menu_mensajeria():
    if not verificar_permiso(1):
        return

    while True:
        if not verificar_permiso(1):
            return

        print("\n==========================================")
        print("               MENSAJERÍA")
        print("==========================================")
        print("1. Listar usuarios disponibles")
        print("2. Enviar mensaje privado")
        print("3. Consultar bandeja de entrada")
        print("4. Consultar mensajes enviados")
        print("5. Consultar conversación")
        print("6. Marcar mensaje como leído")
        print("7. Crear grupo de trabajo")
        print("8. Consultar mis grupos")
        print("9. Agregar miembro a grupo")
        print("10. Enviar mensaje a grupo")
        print("11. Consultar mensajes de grupo")
        print("0. Volver al menú principal")

        opcion = input("\nSeleccione una opción: ").strip()

        if opcion == "1":
            listar_usuarios_mensajeria_service()

        elif opcion == "2":
            enviar_mensaje_service()

        elif opcion == "3":
            consultar_bandeja_service()

        elif opcion == "4":
            consultar_enviados_service()

        elif opcion == "5":
            consultar_conversacion_service()

        elif opcion == "6":
            marcar_leido_service()

        elif opcion == "7":
            crear_grupo_service()

        elif opcion == "8":
            listar_grupos_service()

        elif opcion == "9":
            agregar_miembro_service()

        elif opcion == "10":
            enviar_mensaje_grupo_service()

        elif opcion == "11":
            consultar_mensajes_grupo_service()

        elif opcion == "0":
            break

        else:
            print("\nOpción inválida.")