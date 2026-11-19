"""Pantallas del portal para usuarios de clientes, operadores y proveedores.

La parte (cliente, operador o proveedor) se toma SIEMPRE de la sesión; nunca
se pregunta. Pedir un envío o una factura de otra parte responde "no existe",
para no revelar que existe.
"""

from app.repositories import cuenta_tercero_repository as cuentas
from app.repositories.envio_repository import buscar_envio_por_id
from app.repositories.facturacion_repository import (
    listar_facturas_cliente,
    obtener_detalle_factura,
)
from app.repositories.portal_repository import (
    listar_envios_cliente,
)
from app.repositories.terceros_repository import listar_tramos_operador
from app.services import trazabilidad_service
from app.services.autenticacion import obtener_sesion_actual, parte_de
from app.services.facturacion_service import (
    dinero,
    mostrar_cuenta_cliente,
    mostrar_detalle_factura,
    mostrar_factura,
)
from app.utils import formato
from app.utils.validaciones_terceros import hoy_contable
from app.utils.errores import mensaje_error


NO_EXISTE_ENVIO = "No existe un envío con ese número entre tus envíos."  # lo ajeno se informa como inexistente, para no revelar que existe
NO_EXISTE_FACTURA = "No existe una factura con ese número entre tus facturas."


def pausar():
    input("\nPresioná Enter para continuar...")


def pedir_numero(mensaje):  # pide un número entero positivo
    while True:
        valor = input(mensaje).strip()
        if valor.isdigit() and int(valor) > 0:
            return int(valor)
        print("Ingresá un número entero positivo.")


def parte_actual(*tipos):  # parte e id de la sesión; la usan todas las pantallas del portal
    """Id de la parte de la sesión; error si la sesión no es de esos tipos."""
    tipo, id_parte = parte_de(obtener_sesion_actual())
    if tipo not in tipos:
        raise PermissionError("Esta opción no corresponde a tu usuario.")
    return tipo, id_parte


# ----------------------------------------------------------- cliente

def envio_propio(id_envio, id_cliente):  # el envío solo si es del cliente; la usa _con_envio_propio
    """La fila del envío si es del cliente; si no, None (como si no existiera)."""
    envio = buscar_envio_por_id(id_envio)
    if envio is None or envio[1] != id_cliente:  # uno ajeno se trata igual que uno que no existe
        return None
    return envio


def factura_propia(id_factura, id_cliente):  # la factura solo si es del cliente; la usa detalle_mi_factura_service
    detalle = obtener_detalle_factura(id_factura)
    if detalle is None or detalle["id_cliente"] != id_cliente:
        return None
    return detalle


def mis_envios_service():  # envíos del cliente; opción 1 del portal del cliente
    print("\n--- MIS ENVÍOS ---")
    try:
        _, id_cliente = parte_actual("CLIENTE")
        envios = listar_envios_cliente(id_cliente)  # filtrados por el cliente de la sesión
        if not envios:
            print("Todavía no tiene envíos.")
            return
        for e in envios:
            entrega = (f"entregado {e[8]:%d/%m/%Y %H:%M}" if e[8]
                       else f"llegada estimada {e[9]:%d/%m/%Y}" if e[9]
                       else "sin tramos planificados")
            print(f"Envío {e[0]} | {e[3]} -> {e[4]} | {e[5]} | prioridad {e[6]} | "
                  f"creado {e[7]:%d/%m/%Y} | {entrega}")
    except Exception as error:
        print(f"Error: {mensaje_error(error)}")
    finally:
        pausar()


def _con_envio_propio(funcion_trazabilidad):  # verifica el envío y llama a la pantalla de trazabilidad; la usan las opciones 2 a 4
    """Pide un número de envío, verifica que sea del cliente y lo muestra."""
    try:
        _, id_cliente = parte_actual("CLIENTE")
        envio = envio_propio(pedir_numero("Número de envío: "), id_cliente)
    except Exception as error:
        print(f"Error: {mensaje_error(error)}")
        pausar()
        return
    if envio is None:
        print(NO_EXISTE_ENVIO)
        pausar()
        return
    funcion_trazabilidad(envio)  # le pasa el envío ya verificado


def seguimiento_envio_service():  # opción 2 del portal del cliente
    _con_envio_propio(trazabilidad_service.seguimiento_temporal_service)


def eventos_envio_service():  # opción 3 del portal del cliente
    _con_envio_propio(trazabilidad_service.historial_envio_service)


def ruta_envio_service():  # opción 4 del portal del cliente
    _con_envio_propio(trazabilidad_service.ruta_completa_service)


def quien_llevo_contenedor_service():  # opción 5 del portal del cliente
    # Filtra por el cliente de la sesión (trazabilidad_service.cliente_visible).
    trazabilidad_service.quien_llevo_contenedor_service()


def mis_facturas_service():  # facturas del cliente; opción 6 del portal del cliente
    print("\n--- MIS FACTURAS ---")
    try:
        _, id_cliente = parte_actual("CLIENTE")
        facturas = listar_facturas_cliente(id_cliente)
        if not facturas:
            print("Todavía no tiene facturas.")
        for factura in facturas:
            mostrar_factura(factura)
    except Exception as error:
        print(f"Error: {mensaje_error(error)}")
    finally:
        pausar()


def detalle_mi_factura_service():  # detalle de una factura propia; opción 7 del portal del cliente
    print("\n--- DETALLE DE UNA FACTURA ---")
    try:
        _, id_cliente = parte_actual("CLIENTE")
        detalle = factura_propia(pedir_numero("Número de factura: "), id_cliente)
        if detalle is None:
            print(NO_EXISTE_FACTURA)
            return
        mostrar_detalle_factura(detalle)
    except Exception as error:
        print(f"Error: {mensaje_error(error)}")
    finally:
        pausar()


def mi_cuenta_corriente_service():  # cuenta corriente del cliente; opción 8 del portal del cliente
    print("\n--- MI CUENTA CORRIENTE ---")
    try:
        _, id_cliente = parte_actual("CLIENTE")
        mostrar_cuenta_cliente(id_cliente)
    except Exception as error:
        print(f"Error: {mensaje_error(error)}")
    finally:
        pausar()


def mis_tramos_service():  # tramos del operador; opción 2 del portal del operador
    print("\n--- MIS TRAMOS REALIZADOS ---")
    try:
        _, id_operador = parte_actual("OPERADOR")
        tramos = listar_tramos_operador(id_operador)  # solo los de este operador
        if not tramos:
            print("No tenés tramos asignados.")
            return
        for t in tramos:
            print(f"Tramo {t[0]} | Envío {t[1]} ({t[7]}) | {t[2]} | {t[3]} -> {t[4]} | "
                  f"salida {t[5]:%d/%m/%Y} | "
                  f"{'facturado' if t[8] else 'sin facturar'}")
    except Exception as error:
        print(f"Error: {mensaje_error(error)}")
    finally:
        pausar()


def mi_cuenta_tercero_service():  # facturas y saldo con la empresa; opción 3 del portal del operador y 2 del proveedor
    print("\n--- MIS FACTURAS Y LO QUE LES DEBEMOS ---")
    try:
        tipo, id_parte = parte_actual("OPERADOR", "PROVEEDOR")
        cuenta = cuentas.consultar_cuenta_tercero(tipo, id_parte)  # siempre de la parte de la sesión
        if cuenta is None:
            print("Todavía no hay facturas registradas.")
            return
        print(f"Facturas registradas: {cuenta['cantidad_facturas']} | "
              f"facturado {dinero(cuenta['facturado'])} | "
              f"pagado {dinero(cuenta['pagado'])}")
        print(f"SALDO A SU FAVOR (lo que les debemos): {dinero(cuenta['saldo'])} "
              f"{cuenta['moneda']}")

        pendientes = cuentas.listar_facturas_pendientes(tipo, id_parte)
        if pendientes:
            hoy = hoy_contable()
            print("\nFacturas pendientes de pago:")
            for f in pendientes:
                marca = " VENCIDA" if f[3] < hoy else ""
                print(f"  Comp. {f[1]} | emisión {f[2]:%d/%m/%Y} | vence "
                      f"{f[3]:%d/%m/%Y}{marca} | total {dinero(f[4])} | "
                      f"pendiente {dinero(f[6])} | {f[7]}")

        movimientos = cuentas.listar_movimientos_tercero(tipo, id_parte)
        if movimientos:
            print("\nMovimientos:")
            for fecha, tipo_mov, importe, referencia, detalle in movimientos:
                print(f"  {fecha:%d/%m/%Y} | {dinero(importe):>15} | "
                      f"{formato.descripcion_movimiento(tipo_mov, referencia, detalle)}")
    except Exception as error:
        print(f"Error: {mensaje_error(error)}")
    finally:
        pausar()
