from app.ui.menu_clientes import mostrar_menu_clientes
from app.ui.menu_usuarios import mostrar_menu_usuarios
from app.ui.menu_envios import mostrar_menu_envios
from app.ui.menu_contenedores import mostrar_menu_contenedores
from app.ui.menu_monitoreo import mostrar_menu_monitoreo
from app.ui.menu_trazabilidad import mostrar_menu_trazabilidad
from app.ui.menu_incidentes import mostrar_menu_incidentes
from app.ui.menu_mensajeria import mostrar_menu_mensajeria

from app.services.sesion_service import (
    iniciar_sesion_service,
    cerrar_sesion_service
)

from app.services.autenticacion import (
    obtener_sesion_actual,
    verificar_permiso
)


def ejecutar_modulo(funcion, nivel_minimo=1):
    if verificar_permiso(nivel_minimo):
        funcion()


def mostrar_menu():
    while True:
        try:
            usuario = obtener_sesion_actual()
        except Exception as error:
            print(f"\nError al consultar la sesión: {error}")
            return

        if usuario is None:
            print("\n==========================================")
            print("       SISTEMA DE GESTIÓN LOGÍSTICA")
            print("==========================================")
            print("1. Iniciar sesión")
            print("0. Salir")

            opcion = input("\nSeleccione una opción: ").strip()

            if opcion == "1":
                iniciar_sesion_service()

            elif opcion == "0":
                print("\nCerrando el sistema...")
                break

            else:
                print("\nOpción inválida.")

            continue

        print("\n==========================================")
        print("       SISTEMA DE GESTIÓN LOGÍSTICA")
        print("==========================================")
        print(f"Usuario: {usuario['nombre']} {usuario['apellido']}")
        print(f"Rol: {usuario['rol']}")
        print(f"Nivel de permisos: {usuario['nivel_permisos']}")
        print("------------------------------------------")
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
        print("11. Cerrar sesión")
        print("0. Salir")

        opcion = input("\nSeleccione una opción: ").strip()

        if opcion == "1":
            ejecutar_modulo(mostrar_menu_clientes, 1)

        elif opcion == "2":
            ejecutar_modulo(mostrar_menu_usuarios, 3)

        elif opcion == "3":
            ejecutar_modulo(mostrar_menu_envios, 1)

        elif opcion == "4":
            ejecutar_modulo(mostrar_menu_contenedores, 1)

        elif opcion == "5":
            ejecutar_modulo(mostrar_menu_monitoreo, 1)

        elif opcion == "6":
            ejecutar_modulo(mostrar_menu_trazabilidad, 1)

        elif opcion == "7":
            ejecutar_modulo(mostrar_menu_incidentes, 1)

        elif opcion == "8":
            ejecutar_modulo(mostrar_menu_mensajeria, 1)

        elif opcion == "9":
            if verificar_permiso(1):
                print("\n>> Reportes y facturación")
                print("Módulo pendiente de implementación.")

        elif opcion == "10":
            if verificar_permiso(1):
                print("\n>> Análisis y predicciones")
                print("Módulo pendiente de implementación.")

        elif opcion == "11":
            cerrar_sesion_service()

        elif opcion == "0":
            if cerrar_sesion_service():
                print("\nCerrando el sistema...")
                break
            print("No se pudo cerrar la sesión. Intente nuevamente.")

        else:
            print("\nOpción inválida.")