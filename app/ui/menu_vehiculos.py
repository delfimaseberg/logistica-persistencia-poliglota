from app.services.vehiculo_service import (
    registrar_vehiculo,
    listar_vehiculos_service,
    buscar_vehiculo_service,
    modificar_vehiculo_service,
    eliminar_vehiculo_service
)


def mostrar_menu_vehiculos():
    while True:
        print("\n==========================================")
        print("           GESTIÓN DE VEHÍCULOS")
        print("==========================================")
        print("1. Registrar vehículo")
        print("2. Listar vehículos")
        print("3. Buscar vehículo")
        print("4. Modificar vehículo")
        print("5. Eliminar vehículo")
        print("0. Volver")

        opcion = input("\nSeleccioná una opción: ").strip()

        if opcion == "1":
            registrar_vehiculo()
        elif opcion == "2":
            listar_vehiculos_service()
        elif opcion == "3":
            buscar_vehiculo_service()
        elif opcion == "4":
            modificar_vehiculo_service()
        elif opcion == "5":
            eliminar_vehiculo_service()
        elif opcion == "0":
            break
        else:
            print("Opción inválida.")