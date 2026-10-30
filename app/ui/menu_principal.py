from app.ui.menu_clientes import mostrar_menu_clientes
from app.ui.menu_usuarios import mostrar_menu_usuarios
from app.ui.menu_envios import mostrar_menu_envios
from app.ui.menu_contenedores import mostrar_menu_contenedores
from app.ui.menu_monitoreo import mostrar_menu_monitoreo
from app.ui.menu_trazabilidad import mostrar_menu_trazabilidad
from app.ui.menu_incidentes import mostrar_menu_incidentes
from app.ui.menu_mensajeria import mostrar_menu_mensajeria
from app.ui.menu_facturacion import mostrar_menu_facturacion
from app.ui.menu_reportes import mostrar_menu_reportes
from app.ui.menu_predicciones import mostrar_menu_predicciones
from app.ui.menu_proveedores import mostrar_menu_proveedores
from app.ui.menu_operadores import mostrar_menu_operadores
from app.ui.menu_portal import mostrar_portal

from app.services.sesion_service import (
    iniciar_sesion_service,
    cerrar_sesion_service
)

from app.services.autenticacion import (
    es_interno,
    obtener_sesion_actual,
    verificar_permiso
)


# Menú de usuarios internos: (texto, función, nivel mínimo).
OPCIONES_INTERNAS = {
    "1": ("Gestión de clientes", mostrar_menu_clientes, 1),
    "2": ("Gestión de usuarios", mostrar_menu_usuarios, 3),
    "3": ("Gestión de envíos", mostrar_menu_envios, 1),
    "4": ("Gestión de contenedores y sensores", mostrar_menu_contenedores, 1),
    "5": ("Monitoreo IoT", mostrar_menu_monitoreo, 1),
    "6": ("Trazabilidad de envíos", mostrar_menu_trazabilidad, 1),
    "7": ("Gestión de incidentes y alertas", mostrar_menu_incidentes, 1),
    "8": ("Mensajería", mostrar_menu_mensajeria, 1),
    "9": ("Facturación y cobranzas", mostrar_menu_facturacion, 1),
    "10": ("Reportes", mostrar_menu_reportes, 1),
    "11": ("Análisis y predicciones", mostrar_menu_predicciones, 1),
    "12": ("Proveedores", mostrar_menu_proveedores, 3),
    "13": ("Operadores logísticos", mostrar_menu_operadores, 3),
}
OPCION_CERRAR_SESION = "14"


def ejecutar_modulo(funcion, nivel_minimo=1):
    if verificar_permiso(nivel_minimo):
        funcion()


def menu_para(usuario):
    """Menú interno para la empresa; portal para clientes, operadores y
    proveedores (no ven las funciones internas)."""
    return mostrar_menu_interno if es_interno(usuario) else mostrar_portal


def mostrar_menu_interno(usuario):
    """Una vuelta del menú interno. True = salir del sistema."""
    print("\n==========================================")
    print("       SISTEMA DE GESTIÓN LOGÍSTICA")
    print("==========================================")
    print(f"Usuario: {usuario['nombre']} {usuario['apellido']}")
    print(f"Rol: {usuario['rol']}")
    print(f"Nivel de permisos: {usuario['nivel_permisos']}")
    print("------------------------------------------")
    for clave, (texto, _, _) in OPCIONES_INTERNAS.items():
        print(f"{clave}. {texto}")
    print(f"{OPCION_CERRAR_SESION}. Cerrar sesión")
    print("0. Salir")

    opcion = input("\nSeleccione una opción: ").strip()

    if opcion in OPCIONES_INTERNAS:
        _, funcion, nivel = OPCIONES_INTERNAS[opcion]
        ejecutar_modulo(funcion, nivel)
    elif opcion == OPCION_CERRAR_SESION:
        cerrar_sesion_service()
    elif opcion == "0":
        if cerrar_sesion_service():
            print("\nCerrando el sistema...")
            return True
        print("No se pudo cerrar la sesión. Intente nuevamente.")
    else:
        print("\nOpción inválida.")
    return False


def mostrar_menu():
    while True:
        try:
            usuario = obtener_sesion_actual()
        except Exception as error:
            print(f"\nError al consultar la sesión: {error}")
            return

        if usuario is None:
            print("\n==========================================")
            print("       SISTEMA DE GESTIÓN LOGÍSTICA")
            print("==========================================")
            print("1. Iniciar sesión")
            print("0. Salir")

            opcion = input("\nSeleccione una opción: ").strip()

            if opcion == "1":
                iniciar_sesion_service()
            elif opcion == "0":
                print("\nCerrando el sistema...")
                break
            else:
                print("\nOpción inválida.")
            continue

        if menu_para(usuario)(usuario):
            break
