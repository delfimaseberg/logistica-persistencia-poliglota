from app.ui.menu_clientes import mostrar_menu_clientes
from app.ui.menu_usuarios import mostrar_menu_usuarios
from app.ui.menu_envios import mostrar_menu_envios
from app.ui.menu_contenedores import mostrar_menu_contenedores


def mostrar_menu():
    while True:
        print("\n==========================================")
        print("   SISTEMA DE GESTIÓN LOGÍSTICA")
        print("==========================================")
        print("1. Gestión de clientes")
        print("2. Gestión de usuarios")
        print("3. Gestión de envíos")
        print("4. Gestión de contenedores y sensores")
        print("5. Monitoreo IoT")
        print("6. Trazabilidad de envíos")
        print("7. Gestión de incidentes y alertas")
        print("8. Mensajería")
        print("9. Reportes y facturación")
        print("10. Análisis y predicciones")
        print("0. Salir")

        opcion = input("\nSeleccione una opción: ")

        if opcion == "1":
            mostrar_menu_clientes()
        elif opcion == "2":
            mostrar_menu_usuarios()
        elif opcion == "3":
            mostrar_menu_envios()
        elif opcion == "4":
            mostrar_menu_contenedores()
        elif opcion == "5":
            print("\n>> Monitoreo IoT")
        elif opcion == "6":
            print("\n>> Trazabilidad de envíos")
        elif opcion == "7":
            print("\n>> Gestión de incidentes y alertas")
        elif opcion == "8":
            print("\n>> Mensajería")
        elif opcion == "9":
            print("\n>> Reportes y facturación")
        elif opcion == "10":
            print("\n>> Análisis y predicciones")
        elif opcion == "0":
            print("\nCerrando el sistema...")
            break
        else:
            print("\nOpción inválida. Intente nuevamente.")