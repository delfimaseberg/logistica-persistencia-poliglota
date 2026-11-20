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
from app.services.contrasena_service import cambiar_mi_contrasena_service

from app.services.autenticacion import (
    es_interno,
    obtener_sesion_actual,
    tomar_aviso_cierre,
    verificar_permiso
)
from app.utils.errores import mensaje_error


# Menú de usuarios internos: (texto, función, nivel mínimo).
OPCIONES_INTERNAS = {  # cada opción: texto, menú que abre y nivel mínimo
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
# Cerrar sesión es siempre la última opción antes de Salir (igual que en los portales).
OPCION_CAMBIAR_CONTRASENA = "14"  # van aparte porque no abren un submenú
OPCION_CERRAR_SESION = "15"


def ejecutar_modulo(funcion, nivel_minimo=1):  # abre un menú si el nivel alcanza; la usa mostrar_menu_interno
    if verificar_permiso(nivel_minimo):
        funcion()


def menu_para(usuario):  # elige qué menú ve el usuario según su parte; la usa mostrar_menu
    """Menú interno para la empresa; portal para clientes, operadores y
    proveedores (no ven las funciones internas)."""
    return mostrar_menu_interno if es_interno(usuario) else mostrar_portal  # internos: menú completo; cliente, operador o proveedor: su portal


def mostrar_menu_interno(usuario):  # menú principal de la empresa; lo llama mostrar_menu en cada vuelta
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
    print(f"{OPCION_CAMBIAR_CONTRASENA}. Cambiar mi contraseña")
    print(f"{OPCION_CERRAR_SESION}. Cerrar sesión")
    print("0. Salir")

    opcion = input("\nSeleccioná una opción: ").strip()

    # Si un administrador cerró la sesión mientras se elegía (o venció por
    # inactividad), se avisa antes de interpretar la opción.
    if obtener_sesion_actual() is None:  # también controla la inactividad
        return False

    if opcion in OPCIONES_INTERNAS:
        _, funcion, nivel = OPCIONES_INTERNAS[opcion]
        ejecutar_modulo(funcion, nivel)
    elif opcion == OPCION_CERRAR_SESION:
        cerrar_sesion_service()
    elif opcion == OPCION_CAMBIAR_CONTRASENA:
        cambiar_mi_contrasena_service()
    elif opcion == "0":
        if cerrar_sesion_service():
            print("\nCerrando el sistema...")
            return True
        print("No se pudo cerrar la sesión. Intentá nuevamente.")
    else:
        print("\nOpción inválida.")
    return False


def mostrar_menu():  # ciclo principal del programa; lo llama main.py
    while True:
        try:
            usuario = obtener_sesion_actual()
        except Exception as error:
            print(f"\nError al consultar la sesión: {mensaje_error(error)}")
            return

        if usuario is None:  # sin sesión solo se puede iniciar sesión o salir
            aviso = tomar_aviso_cierre()  # avisa si la sesión la cerró un administrador o la inactividad
            if aviso:
                print(f"\n*** {aviso} ***")
            print("\n==========================================")
            print("       SISTEMA DE GESTIÓN LOGÍSTICA")
            print("==========================================")
            print("1. Iniciar sesión")
            print("0. Salir")

            opcion = input("\nSeleccioná una opción: ").strip()

            if opcion == "1":
                iniciar_sesion_service()
            elif opcion == "0":
                print("\nCerrando el sistema...")
                break
            else:
                print("\nOpción inválida.")
            continue

        if menu_para(usuario)(usuario):  # una vuelta del menú que le toca; True = salir
            break
