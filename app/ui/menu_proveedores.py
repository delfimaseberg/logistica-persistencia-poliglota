from app.services.autenticacion import verificar_permiso
from app.services import terceros_service as servicio


TIPO = "PROVEEDOR"


def mostrar_menu_proveedores():  # menú de proveedores; lo abre la opción 12 del menú principal
    if not verificar_permiso(3):
        return

    while True:
        if not verificar_permiso(3):  # la sesión puede haberse cerrado mientras tanto
            return

        print("\n==========================================")
        print("              PROVEEDORES")
        print("==========================================")
        print("1. Registrar proveedor")
        print("2. Listar proveedores")
        print("3. Buscar proveedor")
        print("4. Modificar proveedor")
        print("5. Dar de baja proveedor (baja lógica)")
        print("6. Reactivar proveedor")
        print("--- Cuenta corriente (lo que les debemos) ---")
        print("7. Registrar factura recibida")
        print("8. Registrar pago a proveedor")
        print("9. Consultar saldo y facturas pendientes")
        print("10. Ver movimientos de la cuenta")
        print("11. Facturas recibidas vencidas o por vencer")
        print("0. Volver al menú principal")

        opcion = input("\nSeleccioná una opción: ").strip()

        acciones = {
            "1": servicio.registrar_tercero_service,
            "2": servicio.listar_terceros_service,
            "3": servicio.buscar_tercero_service,
            "4": servicio.modificar_tercero_service,
            "5": servicio.baja_tercero_service,
            "6": servicio.reactivar_tercero_service,
            "7": servicio.registrar_factura_recibida_service,
            "8": servicio.registrar_pago_emitido_service,
            "9": servicio.consultar_cuenta_tercero_service,
            "10": servicio.movimientos_tercero_service,
        }

        if opcion == "0":
            break
        elif opcion in acciones:
            acciones[opcion](TIPO)  # las mismas pantallas sirven para proveedores y operadores
        elif opcion == "11":  # vencimientos no depende del tipo: lista los de todos
            servicio.vencimientos_service()
        else:
            print("\nOpción inválida.")
