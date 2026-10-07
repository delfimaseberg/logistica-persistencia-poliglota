from app.services.cliente_service import (
    registrar_cliente,
    listar_clientes_service,
    buscar_cliente_service,
    modificar_cliente_service,
    eliminar_cliente_service
)


def mostrar_menu_clientes():
    while True:
        print("\n==========================================")
        print("          GESTIÓN DE CLIENTES")
        print("==========================================")
        print("1. Registrar cliente")
        print("2. Listar clientes")
        print("3. Buscar cliente")
        print("4. Modificar cliente")
        print("5. Eliminar cliente")
        print("0. Volver al menú principal")

        opcion = input("\nSeleccione una opción: ")

        if opcion == "1":
            registrar_cliente()

        elif opcion == "2":
            listar_clientes_service()

        elif opcion == "3":
            buscar_cliente_service()

        elif opcion == "4":
            modificar_cliente_service()

        elif opcion == "5":
            eliminar_cliente_service()

        elif opcion == "0":
            break

        else:
            print("\nOpción inválida. Intente nuevamente.")