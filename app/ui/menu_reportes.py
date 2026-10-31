from app.services.autenticacion import verificar_permiso

from app.services import facturacion_service as servicio
from app.services import reportes_pantallas as pantallas


# (texto, función, nivel mínimo). Solo usuarios internos (verificar_permiso).
OPCIONES = {
    "1": ("Operativos (envíos por país, estado, cliente, demorados, incidentes abiertos)",
          lambda: pantallas.submenu("REPORTES OPERATIVOS", pantallas.REPORTES_OPERATIVOS), 1),
    "2": ("Analíticos (tiempos, incidentes promedio, costos por transporte)",
          lambda: pantallas.submenu("REPORTES ANALÍTICOS", pantallas.REPORTES_ANALITICOS), 1),
    "3": ("Rankings y desempeño",
          lambda: pantallas.submenu("RANKINGS Y DESEMPEÑO", pantallas.REPORTES_RANKINGS), 1),
    "4": ("Reportes cobrables a clientes",
          lambda: pantallas.submenu("REPORTES COBRABLES", pantallas.REPORTES_COBRABLES), 3),
    "5": ("Predictivos (riesgo de demora, rutas que se atrasan, clima)",
          lambda: pantallas.submenu("REPORTES PREDICTIVOS", pantallas.REPORTES_PREDICTIVOS), 1),
    "6": ("Facturación por cliente", servicio.reporte_facturacion_service, 3),
    "7": ("Ingresos mensuales (cobros)", servicio.reporte_ingresos_service, 3),
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
