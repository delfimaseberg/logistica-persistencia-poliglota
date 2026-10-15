
from app.services.autenticacion import verificar_permiso

from app.services.facturacion_service import (
    emitir_factura_service,
    consultar_facturas_service,
    registrar_pago_service,
    consultar_cuenta_corriente_service,
    reporte_facturacion_service,
    reporte_envios_service,
    reporte_ingresos_service
)


def mostrar_menu_facturacion():
    if not verificar_permiso(1):
        return

    while True:
        if not verificar_permiso(1):
            return

        print("\n==========================================")
        print("          REPORTES Y FACTURACIÓN")
        print("==========================================")
        print("1. Emitir factura")
        print("2. Consultar facturas de un cliente")
        print("3. Registrar pago")
        print("4. Consultar cuenta corriente")
        print("5. Reporte de facturación por cliente")
        print("6. Reporte de envíos por estado")
        print("7. Reporte de ingresos mensuales")
        print("0. Volver al menú principal")

        opcion = input("\nSeleccione una opción: ").strip()

        if opcion == "0":
            break

        elif opcion == "1":
            if verificar_permiso(3):
                emitir_factura_service()

        elif opcion == "2":
            if verificar_permiso(3):
                consultar_facturas_service()

        elif opcion == "3":
            if verificar_permiso(3):
                registrar_pago_service()

        elif opcion == "4":
            if verificar_permiso(3):
                consultar_cuenta_corriente_service()

        elif opcion == "5":
            if verificar_permiso(3):
                reporte_facturacion_service()

        elif opcion == "6":
            if verificar_permiso(1):
                reporte_envios_service()

        elif opcion == "7":
            if verificar_permiso(3):
                reporte_ingresos_service()

        else:
            print("\nOpción inválida. Intente nuevamente.")
