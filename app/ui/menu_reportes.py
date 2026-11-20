from app.services.autenticacion import verificar_permiso  # controla sesión, que sea interno y el nivel

from app.services import facturacion_service as servicio  # reportes de facturación e ingresos (opciones 6 y 7)
from app.services import reportes_pantallas as pantallas  # submenús y pantallas de los reportes


# (texto, función, nivel mínimo). Solo usuarios internos (verificar_permiso).
OPCIONES = {  # opciones del menú Reportes: texto, función que abre y nivel mínimo
    "1": ("Operativos (envíos por país, estado, cliente, demorados, incidentes abiertos)",  # submenú de reportes operativos
          lambda: pantallas.submenu("REPORTES OPERATIVOS", pantallas.REPORTES_OPERATIVOS), 1),
    "2": ("Analíticos (tiempos, incidentes promedio, costos por transporte)",  # submenú de reportes analíticos
          lambda: pantallas.submenu("REPORTES ANALÍTICOS", pantallas.REPORTES_ANALITICOS), 1),
    "3": ("Rankings y desempeño",  # submenú de rankings y desempeño
          lambda: pantallas.submenu("RANKINGS Y DESEMPEÑO", pantallas.REPORTES_RANKINGS), 1),
    "4": ("Reportes cobrables a clientes",  # submenú de reportes cobrables; pide nivel 3
          lambda: pantallas.submenu("REPORTES COBRABLES", pantallas.REPORTES_COBRABLES), 3),
    "5": ("Predictivos (riesgo de demora, rutas que se atrasan, clima)",  # submenú de reportes predictivos
          lambda: pantallas.submenu("REPORTES PREDICTIVOS", pantallas.REPORTES_PREDICTIVOS), 1),
    "6": ("Facturación por cliente", servicio.reporte_facturacion_service, 3),  # facturas por cliente, en facturación; nivel 3
    "7": ("Ingresos mensuales (cobros)", servicio.reporte_ingresos_service, 3),  # cobros por mes, en facturación; nivel 3
}


def mostrar_menu_reportes():  # menú Reportes; se abre con la opción 10 del menú interno
    if not verificar_permiso(1):  # hay que ser interno con nivel 1 o más para entrar
        return

    while True:  # repite el menú hasta que se elija 0
        if not verificar_permiso(1):  # vuelve a controlar en cada vuelta, por si la sesión se cerró
            return

        print("\n==========================================")
        print("                REPORTES")
        print("==========================================")
        for clave, (texto, _, _) in OPCIONES.items():  # arma el menú a partir del diccionario
            print(f"{clave}. {texto}")
        print("0. Volver al menú principal")

        opcion = input("\nSeleccioná una opción: ").strip()

        if opcion == "0":
            break

        if opcion in OPCIONES:  # si la opción existe, saca la función y el nivel que pide
            _, funcion, nivel = OPCIONES[opcion]
            if verificar_permiso(nivel):  # cada opción controla su propio nivel
                funcion()
        else:
            print("\nOpción inválida.")
