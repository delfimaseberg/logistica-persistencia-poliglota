from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from app.repositories.facturacion_repository import (
    listar_clientes_facturacion,
    listar_facturas_cliente,
    registrar_pago,
    consultar_cuenta_corriente,
    consultar_movimientos_cuenta,
    reporte_facturacion_clientes,
    reporte_ingresos_mensuales,
    cotizar_envio,
    emitir_factura_envio,
    listar_envios_facturables,
    obtener_detalle_factura,
    estado_facturacion_entregados,
)
from app.repositories import precios_repository
from app.repositories import cierre_cuenta_repository
from app.services import cierre_cuenta_service
from app.services.autenticacion import obtener_sesion_actual, solo_internos
from app.services.facturacion_automatica_service import (
    hoy_argentina,
    procesar_facturacion_automatica,
)
from app.utils import formato
from app.utils.logger import obtener_logger
from app.utils.validaciones_logistica import MEDIOS_TRANSPORTE
from app.utils.errores import mensaje_error
from app.services.autenticacion import requiere_permiso


logger = obtener_logger("facturacion")


def pausar():
    input("\nPresioná Enter para continuar...")


def dinero(valor):
    return formato.dinero(valor)


def pedir_importe(mensaje, permitir_cero=False):
    while True:
        texto = input(mensaje).strip().replace(",", ".")
        try:
            importe = Decimal(texto)
            if importe.is_finite() and (importe > 0 or (permitir_cero and importe == 0)):
                return importe.quantize(Decimal("0.01"))
        except (InvalidOperation, ValueError):
            pass
        print("Ingresá un importe válido"
              + (" (cero o más)." if permitir_cero else " mayor a cero."))


def pedir_entero(mensaje):
    while True:
        texto = input(mensaje).strip()
        if texto.isdigit() and int(texto) > 0:
            return int(texto)
        print("Ingresá un número entero positivo.")


def pedir_fecha(mensaje, por_defecto=None):
    while True:
        texto = input(mensaje).strip()
        if not texto and por_defecto is not None:
            return por_defecto
        try:
            return datetime.strptime(texto, "%Y-%m-%d").date()
        except ValueError:
            print("Usá el formato AAAA-MM-DD.")


def pedir_periodo(mensaje):
    while True:
        texto = input(mensaje).strip()
        try:
            return datetime.strptime(texto, "%Y-%m").date().replace(day=1)
        except ValueError:
            print("Usá el formato AAAA-MM.")


def seleccionar_elemento(elementos, titulo, descripcion, vacio="datos para elegir"):
    if not elementos:
        print(f"\nNo hay {vacio}.")
        return None

    print(f"\n--- {titulo} ---")
    for numero, elemento in enumerate(elementos, 1):
        print(f"{numero}. {descripcion(elemento)}")
    print("0. Cancelar")

    while True:
        opcion = input("\nSeleccioná una opción: ").strip()
        if opcion == "0":
            return None
        if opcion.isdigit() and 1 <= int(opcion) <= len(elementos):
            return elementos[int(opcion) - 1]
        print("Opción inválida.")


def seleccionar_cliente():
    return seleccionar_elemento(
        listar_clientes_facturacion(),
        "SELECCIONAR CLIENTE",
        lambda c: f"{c[1]} | CUIT: {c[2]}",
        "clientes registrados",
    )


def _id_usuario_actual():
    sesion = obtener_sesion_actual()
    return sesion["id_usuario"] if sesion else None


def origen_factura(factura):
    """Texto del origen para listados (columnas de listar_facturas_cliente)."""
    id_envio = factura[6] if len(factura) > 6 else None
    if id_envio is not None:
        return f"Envío {id_envio}"
    return "Histórica (sin envío)"


def mostrar_factura(factura):
    id_factura, fecha, total, estado, pagado, pendiente = factura[:6]
    print("-" * 45)
    print(f"Factura N.º {id_factura} | Fecha: {formato.fecha(fecha)} | {origen_factura(factura)}")
    if len(factura) > 8 and factura[7] is not None:
        print(f"Neto: {dinero(factura[7])} | IVA: {dinero(factura[8])}")
    print(f"Total: {dinero(total)}")
    print(f"Pagado: {dinero(pagado)}")
    print(f"Pendiente: {dinero(pendiente)}")
    print(f"Estado: {estado}")


def mostrar_cotizacion(cotizacion):
    for linea in cotizacion["lineas"]:
        print(f"  {linea['linea']}. {linea['descripcion']:<55} "
              f"{dinero(linea['importe']):>14}")
    print(f"  {'Neto':<58} {dinero(cotizacion['neto']):>14}")
    print(f"  {'IVA 21 %':<58} {dinero(cotizacion['iva']):>14}")
    print(f"  {'TOTAL ' + cotizacion['moneda']:<58} {dinero(cotizacion['total']):>14}")


# ------------------------------------------------------------- facturas

@requiere_permiso(3)
def cotizar_envio_service():
    print("\n--- COTIZAR ENVÍO (sin facturar) ---")
    try:
        id_envio = pedir_entero("ID del envío: ")
        cotizacion = cotizar_envio(id_envio)
        print(f"\nEnvío {id_envio} | Cliente: {cotizacion['cliente']} | "
              f"Estado: {cotizacion['estado_envio']} | "
              f"Tarifa estándar v{cotizacion['version_regla']}")
        mostrar_cotizacion(cotizacion)
        if cotizacion["facturado"]:
            print("\nEste envío ya está facturado.")
        elif str(cotizacion["estado_envio"]).strip().casefold() != "entregado":
            print("\nSe podrá facturar cuando el envío esté Entregado "
                  "(con los precios vigentes en ese momento).")
    except Exception as error:
        print(f"\nNo se pudo cotizar: {mensaje_error(error)}")
    finally:
        pausar()


@requiere_permiso(3)
@solo_internos
def emitir_factura_service():
    print("\n--- EMITIR FACTURA DE UN ENVÍO ENTREGADO ---")
    try:
        cliente = seleccionar_cliente()
        if cliente is None:
            return

        envios = listar_envios_facturables(id_cliente=cliente[0])
        envio = seleccionar_elemento(
            envios,
            f"ENVÍOS ENTREGADOS SIN FACTURA DE {cliente[1]}",
            lambda e: (f"Envío {e[0]} | {e[3]} -> {e[4]} | "
                       f"entregado {e[5]:%d/%m/%Y} | {e[6]} tramo(s)"),
            f"envíos entregados pendientes de facturar para {cliente[1]}",
        )
        if envio is None:
            return

        cotizacion = cotizar_envio(envio[0])
        print(f"\nEnvío {envio[0]} | Tarifa estándar v{cotizacion['version_regla']}")
        mostrar_cotizacion(cotizacion)

        confirmar = input("\n¿Emitir la factura? (S/N): ").strip().upper()
        if confirmar != "S":
            print("Operación cancelada.")
            return

        factura = emitir_factura_envio(envio[0], origen="ENVIO_MANUAL")
        logger.info("Factura %s emitida para el envío %s",
                    factura["id_factura"], envio[0])
        print(f"\nFactura N.º {factura['id_factura']} emitida. "
              f"Total {dinero(factura['total'])} (incluye IVA).")
        if factura["total"] != cotizacion["total"]:
            print("Aviso: el precio cambió entre la cotización y la emisión.")
    except Exception as error:
        print(f"\nError al emitir factura: {mensaje_error(error)}")
    finally:
        pausar()


def mostrar_resumen_automatica(resumen):
    print(f"\nFecha de corte: {resumen['fecha_corte']:%d/%m/%Y} | "
          f"Envíos candidatos: {resumen['candidatos']}")
    print(f"\nFacturados: {len(resumen['facturados'])}")
    for f in resumen["facturados"]:
        print(f"  Envío {f['id_envio']} ({f['cliente']}) -> factura "
              f"{f['id_factura']} por {dinero(f['total'])}")
    print(f"Omitidos: {len(resumen['omitidos'])}")
    for o in resumen["omitidos"]:
        print(f"  Envío {o['id_envio']} ({o['cliente']}): {o['motivo']}")
    print(f"Errores: {len(resumen['errores'])}")
    for e in resumen["errores"]:
        print(f"  Envío {e['id_envio']} ({e['cliente']}): {e['error']}")


@requiere_permiso(3)
@solo_internos
def facturacion_automatica_service():
    print("\n--- FACTURACIÓN AUTOMÁTICA ---")
    print("Factura todos los envíos Entregados sin factura hasta la fecha de corte.")
    try:
        corte = pedir_fecha(
            f"Fecha de corte AAAA-MM-DD [Enter = hoy {hoy_argentina()}]: ",
            hoy_argentina(),
        )
        if input("¿Ejecutar? (S/N): ").strip().upper() != "S":
            print("Operación cancelada.")
            return
        mostrar_resumen_automatica(procesar_facturacion_automatica(corte))
    except Exception as error:
        print(f"\nError en la facturación automática: {mensaje_error(error)}")
    finally:
        pausar()


@requiere_permiso(3)
def consultar_facturas_service():
    print("\n--- CONSULTAR FACTURAS ---")
    try:
        cliente = seleccionar_cliente()
        if cliente is None:
            return

        facturas = listar_facturas_cliente(cliente[0])
        print(f"\nFacturas de {cliente[1]}: {len(facturas)}")

        if not facturas:
            print("El cliente todavía no tiene facturas.")

        for factura in facturas:
            mostrar_factura(factura)

    except Exception as error:
        print(f"Error al consultar facturas: {mensaje_error(error)}")
    finally:
        pausar()


@requiere_permiso(3)
def detalle_factura_service():
    print("\n--- DETALLE DE FACTURA ---")
    try:
        detalle = obtener_detalle_factura(pedir_entero("N.º de factura: "))
        if detalle is None:
            print("No existe esa factura.")
            return
        mostrar_detalle_factura(detalle)
    except Exception as error:
        print(f"Error al consultar la factura: {mensaje_error(error)}")
    finally:
        pausar()


def mostrar_detalle_factura(detalle):
    origen = (f"Envío {detalle['id_envio']}" if detalle["id_envio"]
              else f"Reporte {detalle['id_reporte']}" if detalle["id_reporte"]
              else "Histórica (sin envío)")
    print(f"\nFactura N.º {detalle['id_factura']} | {detalle['cliente']} | "
          f"Emitida {formato.fecha(detalle['fecha_emision'])} | {origen} | {detalle['estado']}")
    if detalle["fecha_entrega"]:
        print(f"Entrega del envío: {detalle['fecha_entrega']:%d/%m/%Y %H:%M}")
    for linea in detalle["lineas"]:
        print(f"  {linea[0]}. {linea[4]:<55} {dinero(linea[5]):>14}")
    if detalle["neto"] is not None:
        print(f"  {'Neto':<58} {dinero(detalle['neto']):>14}")
        print(f"  {'IVA':<58} {dinero(detalle['iva']):>14}")
    print(f"  {'TOTAL':<58} {dinero(detalle['total']):>14}")


@requiere_permiso(3)
def estado_entregados_service():
    print("\n--- ENVÍOS ENTREGADOS: ESTADO DE FACTURACIÓN ---")
    try:
        filas = estado_facturacion_entregados()
        if not filas:
            print("No hay envíos entregados.")
            return
        for (id_envio, cliente, entrega, id_factura, total, tramos,
             con_operador, facturados) in filas:
            factura = (f"factura {id_factura} ({dinero(total)})"
                       if id_factura else "SIN FACTURA al cliente")
            print(f"Envío {id_envio} | {cliente} | entregado {entrega:%d/%m/%Y} | "
                  f"{factura} | tramos: {tramos}, con operador: {con_operador}, "
                  f"facturados por su operador: {facturados}")
    except Exception as error:
        print(f"Error al consultar: {mensaje_error(error)}")
    finally:
        pausar()


# ---------------------------------------------------------------- pagos

@requiere_permiso(3)
@solo_internos
def registrar_pago_service():
    print("\n--- REGISTRAR PAGO ---")
    try:
        cliente = seleccionar_cliente()
        if cliente is None:
            return

        facturas = [
            factura for factura in listar_facturas_cliente(cliente[0])
            if factura[5] > 0 and factura[3].lower() != "anulada"
        ]

        factura = seleccionar_elemento(
            facturas,
            "FACTURAS PENDIENTES",
            lambda f: (
                f"Factura N.º {f[0]} | {origen_factura(f)} | "
                f"Pendiente: {dinero(f[5])}"
            ),
            "facturas pendientes de pago para este cliente",
        )
        if factura is None:
            return

        print(f"\nSaldo pendiente: {dinero(factura[5])}")
        monto = pedir_importe("Monto del pago: ")

        if monto > factura[5]:
            print("El importe supera el saldo pendiente.")
            return

        metodos = ["Transferencia", "Efectivo", "Tarjeta", "Otro"]
        metodo = seleccionar_elemento(
            metodos, "MÉTODO DE PAGO", lambda m: m
        )
        if metodo is None:
            return

        confirmar = input("¿Confirmar pago? (S/N): ").strip().upper()
        if confirmar != "S":
            print("Operación cancelada.")
            return

        id_pago, estado = registrar_pago(factura[0], monto, metodo)
        print(f"\nPago N.º {id_pago} registrado correctamente.")
        print(f"Importe: {dinero(monto)}")
        print(f"Estado de factura: {estado}")

    except Exception as error:
        print(f"Error al registrar pago: {mensaje_error(error)}")
    finally:
        pausar()


@requiere_permiso(3)
def consultar_cuenta_corriente_service():
    print("\n--- CUENTA CORRIENTE ---")
    try:
        cliente = seleccionar_cliente()
        if cliente is None:
            return

        mostrar_cuenta_cliente(cliente[0])

    except Exception as error:
        print(f"Error al consultar cuenta corriente: {mensaje_error(error)}")
    finally:
        pausar()


def mostrar_cuenta_cliente(id_cliente):
    """Totales y movimientos de la cuenta de un cliente (también el portal)."""
    resultado = consultar_cuenta_corriente(id_cliente)
    if resultado is None:
        print("Cliente no encontrado.")
        return

    _, nombre, facturado, pagado = resultado
    print(f"\nCliente: {nombre}")
    print(f"Total facturado: {dinero(facturado)}")
    print(f"Total pagado: {dinero(pagado)}")
    print(f"Saldo pendiente: {dinero(facturado - pagado)}")

    movimientos = consultar_movimientos_cuenta(id_cliente)
    if movimientos:
        print("\nMovimientos registrados en la cuenta:")
        for m in movimientos:
            print(f"  {m[1]:%d/%m/%Y} | {dinero(m[3]):>15} | "
                  f"{formato.descripcion_movimiento(m[5], m[6], m[7])}")


# -------------------------------------------------------------- reportes

@requiere_permiso(3)
def reporte_facturacion_service():
    print("\n--- REPORTE DE FACTURACIÓN POR CLIENTE ---")
    try:
        registros = reporte_facturacion_clientes()
        if not registros:
            print("No hay datos disponibles.")
            return

        for fila in registros:
            _, nombre, cantidad, facturado, cobrado = fila[:5]
            print("-" * 45)
            print(f"Cliente: {nombre}")
            print(f"Facturas: {cantidad}")
            print(f"Facturado: {dinero(facturado)}")
            if len(fila) > 6:
                print(f"  por envíos: {dinero(fila[5])} | "
                      f"históricas sin envío: {dinero(fila[6])}")
            print(f"Cobrado: {dinero(cobrado)}")
            print(f"Pendiente: {dinero(facturado - cobrado)}")

    except Exception as error:
        print(f"Error al generar reporte: {mensaje_error(error)}")
    finally:
        pausar()


@requiere_permiso(3)
def reporte_ingresos_service():
    print("\n--- INGRESOS MENSUALES ---")
    try:
        registros = reporte_ingresos_mensuales()
        if not registros:
            print("Todavía no hay pagos registrados.")
            return

        for mes, cantidad, total in registros:
            print(
                f"{formato.mes(mes)} | Pagos: {cantidad} | "
                f"Recaudado: {dinero(total)}"
            )

    except Exception as error:
        print(f"Error al consultar ingresos: {mensaje_error(error)}")
    finally:
        pausar()


# --------------------------------------------------------------- precios

@requiere_permiso(3)
@solo_internos
def precios_transporte_service():
    print("\n--- PRECIOS DE TRANSPORTE (tarifa estándar, ARS, sin IVA) ---")
    try:
        actual = precios_repository.obtener_tarifa_estandar()
        if actual is None:
            print("Todavía no hay precios definidos.")
        else:
            print(f"Versión vigente: {actual['version']} (desde "
                  f"{actual['vigente_desde']:%d/%m/%Y}, ref. {actual['referencia']})")
            print(f"  Cargo base por envío: {dinero(actual['base'])}")
            for medio in MEDIOS_TRANSPORTE:
                precio = actual["precios"].get(medio)
                print(f"  Tramo {medio}: "
                      + (dinero(precio) if precio is not None else "sin precio"))

        if input("\n¿Definir precios nuevos? (S/N): ").strip().upper() != "S":
            return

        base = pedir_importe("Cargo base por envío: ", permitir_cero=True)
        precios = {medio: pedir_importe(f"Precio por tramo {medio}: ")
                   for medio in MEDIOS_TRANSPORTE}
        referencia = input("Referencia del cambio (ej. lista de precios 2026-11): ")
        print("Rige desde hoy para las facturas que se emitan; las ya "
              "emitidas no cambian.")
        if input("¿Confirmar? (S/N): ").strip().upper() != "S":
            print("Operación cancelada.")
            return

        id_regla = precios_repository.definir_tarifa_estandar(
            base, precios, _id_usuario_actual(), referencia
        )
        logger.info("Tarifa estándar nueva: regla %s", id_regla)
        print(f"\nPrecios aprobados (regla {id_regla}). La versión anterior "
              "queda reemplazada y se conserva.")
    except Exception as error:
        print(f"\nError: {mensaje_error(error)}")
    finally:
        pausar()


# ------------------------------------------------- apertura y cierre

@requiere_permiso(3)
@solo_internos
def apertura_cuenta_service():
    print("\n--- APERTURA DE CUENTA CORRIENTE ---")
    try:
        aperturas = cierre_cuenta_repository.listar_aperturas()
        if aperturas:
            print("Aperturas registradas:")
            for a in aperturas:
                print(f"  {a[2]}: {dinero(a[3])} {a[4]} desde {a[5]:%d/%m/%Y} | "
                      f"ref. {a[6]} | aprobó {a[7]}")

        sesion = obtener_sesion_actual()
        if sesion is None or any(
            sesion.get(parte) is not None
            for parte in ("id_cliente", "id_proveedor", "id_operador")
        ):
            print("\nSolo un usuario interno puede aprobar una apertura.")
            return

        if input("\n¿Registrar una apertura? (S/N): ").strip().upper() != "S":
            return

        cliente = seleccionar_cliente()
        if cliente is None:
            return
        fecha = pedir_fecha("Fecha de vigencia AAAA-MM-DD: ")
        _, _, sugerido = cierre_cuenta_repository.calcular_saldo_documentos(
            cliente[0], fecha
        )
        print(f"Saldo según facturas y pagos anteriores a esa fecha: "
              f"{dinero(sugerido)}")
        texto = input(f"Saldo inicial [Enter = {sugerido}]: ").strip()
        saldo = Decimal(texto.replace(",", ".")) if texto else sugerido
        referencia = input("Referencia documentada: ")

        vista = cierre_cuenta_service.previsualizar_apertura(cliente[0], saldo, fecha)
        if vista["concilia"]:
            s = vista["snapshot"]
            print(f"\nCon esta apertura la cuenta concilia. Cierre de "
                  f"{fecha:%m/%Y}: inicial {dinero(s['saldo_inicial'])}, "
                  f"facturas {dinero(s['total_facturas'])}, pagos "
                  f"{dinero(s['total_pagos'])}, final {dinero(s['saldo_final'])}.")
        else:
            print(f"\nAtención: con esta apertura el cierre quedaría bloqueado: "
                  f"{vista['motivo']}")

        print(f"Aprobación a cargo de: {sesion['nombre']} {sesion['apellido']}")
        if input("¿Registrar y aprobar la apertura? (S/N): ").strip().upper() != "S":
            print("Operación cancelada.")
            return
        id_apertura = cierre_cuenta_service.registrar_apertura(
            cliente[0], saldo, fecha, referencia, sesion["id_usuario"]
        )
        print(f"\nApertura {id_apertura} registrada.")
    except Exception as error:
        print(f"\nError: {mensaje_error(error)}")
    finally:
        pausar()


def mostrar_resumen_cierre(resumen):
    print(f"\nPeríodo {resumen['periodo']:%m/%Y}")
    print(f"Cerrados: {len(resumen['cerrados'])}")
    for c in resumen["cerrados"]:
        print(f"  {c['cliente']}: inicial {dinero(c['saldo_inicial'])} + facturas "
              f"{dinero(c['total_facturas'])} - pagos {dinero(c['total_pagos'])} "
              f"= final {dinero(c['saldo_final'])} (cierre {c['id_cierre']})")
    print(f"Bloqueados: {len(resumen['bloqueados'])}")
    for b in resumen["bloqueados"]:
        print(f"  {b['cliente']}: {b['motivo']}")
    print(f"Ya cerrados antes: {len(resumen['ya_cerrados'])}")
    for y in resumen["ya_cerrados"]:
        print(f"  {y['cliente']}")
    print(f"Errores: {len(resumen['errores'])}")
    for e in resumen["errores"]:
        print(f"  {e['cliente']}: {e['error']}")


@requiere_permiso(3)
@solo_internos
def cierre_mensual_service():
    print("\n--- CIERRE MENSUAL DE CUENTAS CORRIENTES ---")
    try:
        periodo = pedir_periodo("Período a cerrar (AAAA-MM): ")
        print("El cierre es definitivo: guarda un resumen inmutable por cliente.")
        if input("¿Cerrar el período para todos los clientes? (S/N): ").strip().upper() != "S":
            print("Operación cancelada.")
            return
        mostrar_resumen_cierre(cierre_cuenta_service.cerrar_mes_todos(periodo))
    except Exception as error:
        print(f"\nError en el cierre: {mensaje_error(error)}")
    finally:
        pausar()
