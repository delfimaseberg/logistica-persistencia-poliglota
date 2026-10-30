"""Portales para usuarios de clientes, operadores y proveedores.

Cada función devuelve True si el usuario eligió salir del sistema y False
si cerró la sesión (o la sesión dejó de ser válida).
"""

from app.services import portal_service as portal
from app.services.autenticacion import obtener_sesion_actual, parte_de
from app.services.sesion_service import cerrar_sesion_service
from app.ui.menu_mensajeria import mostrar_menu_mensajeria


OPCIONES_CLIENTE = {
    "1": ("Mis envíos", portal.mis_envios_service),
    "2": ("Seguimiento de un envío (línea de tiempo)", portal.seguimiento_envio_service),
    "3": ("Eventos de un envío", portal.eventos_envio_service),
    "4": ("Ruta y operadores de un envío", portal.ruta_envio_service),
    "5": ("¿Quién llevó mi contenedor?", portal.quien_llevo_contenedor_service),
    "6": ("Mis facturas", portal.mis_facturas_service),
    "7": ("Detalle de una factura", portal.detalle_mi_factura_service),
    "8": ("Mi cuenta corriente", portal.mi_cuenta_corriente_service),
    "9": ("Mis reportes", portal.mis_reportes_service),
    "10": ("Mensajería", mostrar_menu_mensajeria),
}

OPCIONES_OPERADOR = {
    "1": ("Mensajería", mostrar_menu_mensajeria),
    "2": ("Mis tramos realizados", portal.mis_tramos_service),
    "3": ("Mis facturas y lo que nos falta pagarles", portal.mi_cuenta_tercero_service),
}

OPCIONES_PROVEEDOR = {
    "1": ("Mensajería", mostrar_menu_mensajeria),
    "2": ("Mis facturas y lo que nos falta pagarles", portal.mi_cuenta_tercero_service),
}

TITULOS = {
    "CLIENTE": "PORTAL DEL CLIENTE",
    "OPERADOR": "PORTAL DEL OPERADOR LOGÍSTICO",
    "PROVEEDOR": "PORTAL DEL PROVEEDOR",
}
OPCIONES_POR_PARTE = {
    "CLIENTE": OPCIONES_CLIENTE,
    "OPERADOR": OPCIONES_OPERADOR,
    "PROVEEDOR": OPCIONES_PROVEEDOR,
}


def mostrar_portal(usuario):
    tipo, _ = parte_de(usuario)
    opciones = OPCIONES_POR_PARTE[tipo]
    cerrar = str(len(opciones) + 1)

    while True:
        usuario = obtener_sesion_actual()
        if usuario is None or parte_de(usuario)[0] != tipo:
            return False

        print("\n==========================================")
        print(f"   {TITULOS[tipo]}")
        print("==========================================")
        print(f"Usuario: {usuario['nombre']} {usuario['apellido']}")
        print("------------------------------------------")
        for clave, (texto, _) in opciones.items():
            print(f"{clave}. {texto}")
        print(f"{cerrar}. Cerrar sesión")
        print("0. Salir")

        opcion = input("\nSeleccione una opción: ").strip()

        if opcion in opciones:
            opciones[opcion][1]()
        elif opcion == cerrar:
            cerrar_sesion_service()
            return False
        elif opcion == "0":
            if cerrar_sesion_service():
                print("\nCerrando el sistema...")
                return True
            print("No se pudo cerrar la sesión. Intente nuevamente.")
        else:
            print("\nOpción inválida.")
