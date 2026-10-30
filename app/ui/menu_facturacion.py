from app.services.autenticacion import verificar_permiso

from app.services import facturacion_service as servicio


# (texto, función, nivel mínimo). Solo usuarios internos (verificar_permiso).
OPCIONES = {
    "1": ("Cotizar un envío (sin facturar)", servicio.cotizar_envio_service, 3),
    "2": ("Emitir factura de un envío entregado", servicio.emitir_factura_service, 3),
    "3": ("Facturación automática (envíos entregados hasta una fecha de corte)",
          servicio.facturacion_automatica_service, 3),
    "4": ("Consultar facturas de un cliente", servicio.consultar_facturas_service, 3),
    "5": ("Ver detalle de una factura", servicio.detalle_factura_service, 3),
    "6": ("Registrar pago de un cliente", servicio.registrar_pago_service, 3),
    "7": ("Consultar cuenta corriente de un cliente",
          servicio.consultar_cuenta_corriente_service, 3),
    "8": ("Envíos entregados: estado de facturación (cliente y operadores)",
          servicio.estado_entregados_service, 3),
    "9": ("Precios de transporte (tarifa estándar)",
          servicio.precios_transporte_service, 3),
    "10": ("Apertura de cuenta corriente", servicio.apertura_cuenta_service, 3),
    "11": ("Cierre mensual de cuentas corrientes", servicio.cierre_mensual_service, 3),
}


def mostrar_menu_facturacion():
    if not verificar_permiso(1):
        return

    while True:
        if not verificar_permiso(1):
            return

        print("\n==========================================")
        print("        FACTURACIÓN Y COBRANZAS")
        print("==========================================")
        for clave, (texto, _, _) in OPCIONES.items():
            print(f"{clave}. {texto}")
        print("12. Reglas tarifarias y datos de carga (avanzado)")
        print("0. Volver al menú principal")

        opcion = input("\nSeleccione una opción: ").strip()

        if opcion == "0":
            break

        if opcion in OPCIONES:
            _, funcion, nivel = OPCIONES[opcion]
            if verificar_permiso(nivel):
                funcion()

        elif opcion == "12":
            if verificar_permiso(3):
                from app.ui.menu_tarifas import mostrar_menu_tarifas
                mostrar_menu_tarifas()

        else:
            print("\nOpción inválida. Intente nuevamente.")
