from app.services.contenedor_service import registrar_contenedor, registrar_sensor


def mostrar_menu_contenedores():
    while True:
        print("\n==========================================")
        print("      CONTENEDORES Y SENSORES")
        print("==========================================")
        print("1. Registrar contenedor")
        print("2. Listar contenedores")
        print("3. Buscar contenedor")
        print("4. Modificar contenedor")
        print("5. Registrar sensor")
        print("6. Listar sensores de un contenedor")
        print("0. Volver al menú principal")

        opcion = input("\nSeleccione una opción: ")

        if opcion == "1":
            registrar_contenedor()
        elif opcion == "2":
            print("\n>> Listar contenedores")
        elif opcion == "3":
            print("\n>> Buscar contenedor")
        elif opcion == "4":
            print("\n>> Modificar contenedor")
        elif opcion == "5":
            registrar_sensor()
        elif opcion == "6":
            print("\n>> Listar sensores")
        elif opcion == "0":
            break
        else:
            print("\nOpción inválida. Intente nuevamente.")