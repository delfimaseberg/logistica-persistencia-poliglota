from app.services.envio_service import registrar_envio, registrar_tramo


def mostrar_menu_envios():
    while True:
        print("\n==========================================")
        print("           GESTIÓN DE ENVÍOS")
        print("==========================================")
        print("1. Registrar envío")
        print("2. Listar envíos")
        print("3. Buscar envío")
        print("4. Modificar envío")
        print("5. Registrar tramo")
        print("6. Consultar tramos de un envío")
        print("7. Asociar contenedor a envío")
        print("0. Volver al menú principal")

        opcion = input("\nSeleccione una opción: ")

        if opcion == "1":
            registrar_envio()
        elif opcion == "2":
            print("\n>> Listar envíos")
        elif opcion == "3":
            print("\n>> Buscar envío")
        elif opcion == "4":
            print("\n>> Modificar envío")
        elif opcion == "5":
            registrar_tramo()
        elif opcion == "6":
            print("\n>> Consultar tramos")
        elif opcion == "7":
            print("\n>> Asociar contenedor a envío")
        elif opcion == "0":
            break
        else:
            print("\nOpción inválida. Intente nuevamente.")