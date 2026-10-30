from app.services.autenticacion import verificar_permiso

from app.services import facturacion_service as servicio


# (texto, función, nivel mínimo). Los reportes analíticos y los reportes
# solicitados por clientes se agregan aquí (día 3).
OPCIONES = {
    "1": ("Envíos por estado", servicio.reporte_envios_service, 1),
    "2": ("Facturación por cliente", servicio.reporte_facturacion_service, 3),
    "3": ("Ingresos mensuales (cobros)", servicio.reporte_ingresos_service, 3),
}


def mostrar_menu_reportes():
    if not verificar_permiso(1):
        return

    while True:
        if not verificar_permiso(1):
            return

        print("\n==========================================")
        print("                REPORTES")
        print("==========================================")
        for clave, (texto, _, _) in OPCIONES.items():
            print(f"{clave}. {texto}")
        print("0. Volver al menú principal")

        opcion = input("\nSeleccione una opción: ").strip()

        if opcion == "0":
            break

        if opcion in OPCIONES:
            _, funcion, nivel = OPCIONES[opcion]
            if verificar_permiso(nivel):
                funcion()
        else:
            print("\nOpción inválida.")
