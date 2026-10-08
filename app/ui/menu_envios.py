from app.services.envio_service import (
    registrar_envio,
    listar_envios_service,
    buscar_envio_service,
    modificar_envio_service,
    eliminar_envio_service
)

from app.services.tramo_service import (
    registrar_tramo,
    consultar_tramos_service
)

from app.services.envio_contenedor_service import (
    asociar_contenedor_service,
    consultar_contenedores_envio_service,
    desasociar_contenedor_service
)

from app.ui.menu_vehiculos import mostrar_menu_vehiculos


def mostrar_menu_envios():
    while True:
        print("\n==========================================")
        print("           GESTIÓN DE ENVÍOS")
        print("==========================================")
        print("1. Registrar envío")
        print("2. Listar envíos")
        print("3. Buscar envío")
        print("4. Modificar envío")
        print("5. Eliminar envío")
        print("6. Gestión de vehículos")
        print("7. Registrar tramo")
        print("8. Consultar tramos de un envío")
        print("9. Asociar contenedor a envío")
        print("10. Consultar contenedores de un envío")
        print("11. Desasociar contenedor")
        print("0. Volver al menú principal")

        opcion = input("\nSeleccione una opción: ").strip()

        if opcion == "1":
            registrar_envio()
        elif opcion == "2":
            listar_envios_service()
        elif opcion == "3":
            buscar_envio_service()
        elif opcion == "4":
            modificar_envio_service()
        elif opcion == "5":
            eliminar_envio_service()
        elif opcion == "6":
            mostrar_menu_vehiculos()
        elif opcion == "7":
            registrar_tramo()
        elif opcion == "8":
            consultar_tramos_service()
        elif opcion == "9":
            asociar_contenedor_service()
        elif opcion == "10":
            consultar_contenedores_envio_service()
        elif opcion == "11":
            desasociar_contenedor_service()
        elif opcion == "0":
            break
        else:
            print("Opción inválida.")