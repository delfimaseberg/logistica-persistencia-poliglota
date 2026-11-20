from app.services.envio_service import (  # pantallas del ABM de envíos
    registrar_envio,
    listar_envios_service,
    buscar_envio_service,
    modificar_envio_service,
    eliminar_envio_service
)

from app.services.tramo_service import (  # pantallas para cargar y ver los tramos
    registrar_tramo,
    consultar_tramos_service
)

from app.services.envio_contenedor_service import (  # pantallas para asociar contenedores a un envío
    asociar_contenedor_service,
    consultar_contenedores_envio_service,
    desasociar_contenedor_service
)

from app.ui.menu_vehiculos import mostrar_menu_vehiculos  # submenú de vehículos (opción 6)


def mostrar_menu_envios():  # menú de Gestión de envíos; se abre con la opción 3 del menú interno
    while True:  # repite el menú hasta que se elija 0
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

        opcion = input("\nSeleccioná una opción: ").strip()

        if opcion == "1":  # alta de un envío nuevo
            registrar_envio()
        elif opcion == "2":  # lista todos los envíos con su cliente
            listar_envios_service()
        elif opcion == "3":  # busca un envío por su ID
            buscar_envio_service()
        elif opcion == "4":  # cambia un dato del envío (cliente, ruta, estado, prioridad o países)
            modificar_envio_service()
        elif opcion == "5":  # borra un envío que no esté entregado
            eliminar_envio_service()
        elif opcion == "6":  # vehículos, que después se usan en los tramos
            mostrar_menu_vehiculos()
        elif opcion == "7":  # agrega un tramo al recorrido del envío
            registrar_tramo()
        elif opcion == "8":  # muestra los tramos del envío en orden de salida
            consultar_tramos_service()
        elif opcion == "9":  # asigna un contenedor al envío
            asociar_contenedor_service()
        elif opcion == "10":  # lista los contenedores que tiene el envío
            consultar_contenedores_envio_service()
        elif opcion == "11":  # saca un contenedor del envío
            desasociar_contenedor_service()
        elif opcion == "0":  # vuelve al menú principal
            break
        else:
            print("Opción inválida.")