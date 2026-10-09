from app.services.autenticacion import verificar_permiso

from app.services.lectura_iot_service import (
    registrar_lectura_service,
    consultar_lecturas_sensor_service,
    consultar_lecturas_contenedor_service,
    consultar_ultima_lectura_service
)


def mostrar_menu_monitoreo():
    if not verificar_permiso(1):
        return

    while True:
        if not verificar_permiso(1):
            return

        print("\n==========================================")
        print("             MONITOREO IoT")
        print("==========================================")
        print("1. Registrar lectura IoT")
        print("2. Consultar lecturas por sensor")
        print("3. Consultar lecturas por contenedor")
        print("4. Consultar última lectura de un sensor")
        print("0. Volver al menú principal")

        opcion = input("\nSeleccione una opción: ").strip()

        if opcion == "1":
            registrar_lectura_service()

        elif opcion == "2":
            consultar_lecturas_sensor_service()

        elif opcion == "3":
            consultar_lecturas_contenedor_service()

        elif opcion == "4":
            consultar_ultima_lectura_service()

        elif opcion == "0":
            break

        else:
            print("\nOpción inválida.")