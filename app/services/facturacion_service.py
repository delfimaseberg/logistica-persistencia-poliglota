
from decimal import Decimal, InvalidOperation

from app.repositories.facturacion_repository import (
    listar_clientes_facturacion,
    listar_facturas_cliente,
    emitir_factura,
    registrar_pago,
    consultar_cuenta_corriente,
    reporte_facturacion_clientes,
    reporte_envios_estado,
    reporte_ingresos_mensuales
)


def pausar():
    input("\nPresioná Enter para continuar...")


def dinero(valor):
    return f"${valor:,.2f}"


def pedir_importe(mensaje):
    while True:
        texto = input(mensaje).strip().replace(",", ".")
        try:
            importe = Decimal(texto)
            if importe.is_finite() and importe > 0:
                return importe.quantize(Decimal("0.01"))
        except (InvalidOperation, ValueError):
            pass
        print("Ingresá un importe válido mayor a cero.")


def seleccionar_elemento(elementos, titulo, descripcion):
    if not elementos:
        print("\nNo hay registros disponibles.")
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
        lambda c: f"{c[1]} | CUIT: {c[2]}"
    )


def mostrar_factura(factura):
    id_factura, fecha, total, estado, pagado, pendiente = factura
    print("-" * 45)
    print(f"Factura N.º {id_factura} | Fecha: {fecha}")
    print(f"Total: {dinero(total)}")
    print(f"Pagado: {dinero(pagado)}")
    print(f"Pendiente: {dinero(pendiente)}")
    print(f"Estado: {estado}")


def emitir_factura_service():
    print("\n--- EMITIR FACTURA ---")
    try:
        cliente = seleccionar_cliente()
        if cliente is None:
            return

        print(f"\nCliente: {cliente[1]}")
        importe = pedir_importe("Importe total: ")

        confirmar = input("¿Confirmar factura? (S/N): ").strip().upper()
        if confirmar != "S":
            print("Operación cancelada.")
            return

        id_factura = emitir_factura(cliente[0], importe)
        print(f"\nFactura N.º {id_factura} emitida correctamente.")
        print(f"Total: {dinero(importe)}")
        print("Estado: Pendiente")

    except Exception as error:
        print(f"Error al emitir factura: {error}")
    finally:
        pausar()


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
        print(f"Error al consultar facturas: {error}")
    finally:
        pausar()


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
                f"Factura N.º {f[0]} | "
                f"Pendiente: {dinero(f[5])}"
            )
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
        print(f"Error al registrar pago: {error}")
    finally:
        pausar()


def consultar_cuenta_corriente_service():
    print("\n--- CUENTA CORRIENTE ---")
    try:
        cliente = seleccionar_cliente()
        if cliente is None:
            return

        resultado = consultar_cuenta_corriente(cliente[0])
        if resultado is None:
            print("Cliente no encontrado.")
            return

        _, nombre, facturado, pagado = resultado
        print(f"\nCliente: {nombre}")
        print(f"Total facturado: {dinero(facturado)}")
        print(f"Total pagado: {dinero(pagado)}")
        print(f"Saldo pendiente: {dinero(facturado - pagado)}")

    except Exception as error:
        print(f"Error al consultar cuenta corriente: {error}")
    finally:
        pausar()


def reporte_facturacion_service():
    print("\n--- REPORTE DE FACTURACIÓN POR CLIENTE ---")
    try:
        registros = reporte_facturacion_clientes()
        if not registros:
            print("No hay datos disponibles.")
            return

        for _, nombre, cantidad, facturado, cobrado in registros:
            print("-" * 45)
            print(f"Cliente: {nombre}")
            print(f"Facturas: {cantidad}")
            print(f"Facturado: {dinero(facturado)}")
            print(f"Cobrado: {dinero(cobrado)}")
            print(f"Pendiente: {dinero(facturado - cobrado)}")

    except Exception as error:
        print(f"Error al generar reporte: {error}")
    finally:
        pausar()


def reporte_envios_service():
    print("\n--- REPORTE DE ENVÍOS POR ESTADO ---")
    try:
        registros = reporte_envios_estado()
        if not registros:
            print("No hay envíos registrados.")
            return

        total = sum(cantidad for _, cantidad in registros)
        for estado, cantidad in registros:
            porcentaje = cantidad * 100 / total
            print(f"{estado}: {cantidad} ({porcentaje:.1f}%)")
        print(f"\nTotal de envíos: {total}")

    except Exception as error:
        print(f"Error al generar reporte: {error}")
    finally:
        pausar()


def reporte_ingresos_service():
    print("\n--- INGRESOS MENSUALES ---")
    try:
        registros = reporte_ingresos_mensuales()
        if not registros:
            print("Todavía no hay pagos registrados.")
            return

        for mes, cantidad, total in registros:
            print(
                f"{mes} | Pagos: {cantidad} | "
                f"Recaudado: {dinero(total)}"
            )

    except Exception as error:
        print(f"Error al consultar ingresos: {error}")
    finally:
        pausar()
