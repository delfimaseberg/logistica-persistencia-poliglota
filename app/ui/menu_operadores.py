from app.services.autenticacion import verificar_permiso
from app.services import terceros_service as servicio


TIPO = "OPERADOR"


def mostrar_menu_operadores():
    if not verificar_permiso(3):
        return

    while True:
        if not verificar_permiso(3):
            return

        print("\n==========================================")
        print("          OPERADORES LOGÍSTICOS")
        print("==========================================")
        print("1. Registrar operador")
        print("2. Listar operadores")
        print("3. Buscar operador")
        print("4. Modificar operador")
        print("5. Dar de baja operador (baja lógica)")
        print("6. Reactivar operador")
        print("--- Tramos ---")
        print("7. Tramos realizados por un operador")
        print("8. Asignar operador a un vehículo")
        print("9. Asignar operador a un tramo sin operador")
        print("--- Cuenta corriente (lo que les debemos) ---")
        print("10. Registrar factura recibida (por tramo de envío entregado)")
        print("11. Registrar pago a operador")
        print("12. Consultar saldo y facturas pendientes")
        print("13. Ver movimientos de la cuenta")
        print("14. Facturas recibidas vencidas o por vencer")
        print("0. Volver al menú principal")

        opcion = input("\nSeleccione una opción: ").strip()

        acciones = {
            "1": servicio.registrar_tercero_service,
            "2": servicio.listar_terceros_service,
            "3": servicio.buscar_tercero_service,
            "4": servicio.modificar_tercero_service,
            "5": servicio.baja_tercero_service,
            "6": servicio.reactivar_tercero_service,
            "10": servicio.registrar_factura_recibida_service,
            "11": servicio.registrar_pago_emitido_service,
            "12": servicio.consultar_cuenta_tercero_service,
            "13": servicio.movimientos_tercero_service,
        }
        sin_tipo = {
            "7": servicio.tramos_operador_service,
            "8": servicio.asignar_operador_vehiculo_service,
            "9": servicio.asignar_operador_tramo_service,
            "14": servicio.vencimientos_service,
        }

        if opcion == "0":
            break
        elif opcion in acciones:
            acciones[opcion](TIPO)
        elif opcion in sin_tipo:
            sin_tipo[opcion]()
        else:
            print("\nOpción inválida.")
