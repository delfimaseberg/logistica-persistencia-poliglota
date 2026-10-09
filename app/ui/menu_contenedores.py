
from app.services.contenedor_service import (
    registrar_contenedor,
    listar_contenedores_service,
    buscar_contenedor_service,
    modificar_contenedor_service,
    eliminar_contenedor_service
)

from app.services.sensor_service import (
    registrar_sensor,
    listar_sensores_service,
    buscar_sensor_service,
    consultar_sensores_contenedor_service,
    modificar_sensor_service,
    eliminar_sensor_service
)


def mostrar_menu_contenedores():
    while True:
        print("\n==========================================")
        print("       GESTIÓN DE CONTENEDORES Y SENSORES")
        print("==========================================")

        print("\n--- CONTENEDORES ---")
        print("1. Registrar contenedor")
        print("2. Listar contenedores")
        print("3. Buscar contenedor")
        print("4. Modificar contenedor")
        print("5. Eliminar contenedor")

        print("\n--- SENSORES IoT ---")
        print("6. Registrar sensor")
        print("7. Listar sensores")
        print("8. Buscar sensor")
        print("9. Consultar sensores de un contenedor")
        print("10. Modificar sensor")
        print("11. Dar de baja sensor")

        print("\n0. Volver al menú principal")

        opcion = input("\nSeleccione una opción: ").strip()

        if opcion == "1":
            registrar_contenedor()
        elif opcion == "2":
            listar_contenedores_service()
        elif opcion == "3":
            buscar_contenedor_service()
        elif opcion == "4":
            modificar_contenedor_service()
        elif opcion == "5":
            eliminar_contenedor_service()
        elif opcion == "6":
            registrar_sensor()
        elif opcion == "7":
            listar_sensores_service()
        elif opcion == "8":
            buscar_sensor_service()
        elif opcion == "9":
            consultar_sensores_contenedor_service()
        elif opcion == "10":
            modificar_sensor_service()
        elif opcion == "11":
            eliminar_sensor_service()
        elif opcion == "0":
            break
        else:
            print("\nOpción inválida.")
