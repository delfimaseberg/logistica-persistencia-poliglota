"""Pantallas de proveedores y operadores logísticos: ABM y cuenta corriente.

Las mismas funciones sirven para los dos tipos ("PROVEEDOR" u "OPERADOR").
"""

from datetime import date, datetime

from app.repositories import terceros_repository as repo
from app.repositories import cuenta_tercero_repository as cuentas
from app.services.autenticacion import obtener_sesion_actual, solo_internos
from app.services.sincronizacion_service import sincronizar_envio_neo4j
from app.utils import formato
from app.utils.logger import obtener_logger
from app.utils.validaciones import (
    texto_obligatorio,
    validar_email,
    validar_telefono,
)
from app.utils.validaciones_terceros import (
    DIAS_VENCIMIENTO_DEFECTO,
    RUBROS_PROVEEDOR,
    hoy_contable,
    validar_cuit,
    validar_modalidades,
    validar_rubro,
)
from app.utils.validaciones_logistica import MEDIOS_TRANSPORTE
from app.utils.errores import mensaje_error
from app.utils.validaciones_datos import (
    LARGOS_CONTACTO,
    validar_email as validar_email_dato,
    validar_largo,
    validar_telefono as validar_telefono_dato,
)
from app.services.autenticacion import requiere_permiso


logger = obtener_logger("terceros")

NOMBRES = {"PROVEEDOR": "proveedor", "OPERADOR": "operador logístico"}

_FUNCIONES = {
    "PROVEEDOR": {
        "crear": repo.crear_proveedor,
        "listar": repo.listar_proveedores,
        "buscar": repo.buscar_proveedor,
        "por_cuit": repo.buscar_proveedor_por_cuit,
        "modificar": repo.modificar_proveedor,
        "baja": repo.dar_de_baja_proveedor,
        "reactivar": repo.reactivar_proveedor,
    },
    "OPERADOR": {
        "crear": repo.crear_operador,
        "listar": repo.listar_operadores,
        "buscar": repo.buscar_operador,
        "por_cuit": repo.buscar_operador_por_cuit,
        "modificar": repo.modificar_operador,
        "baja": repo.dar_de_baja_operador,
        "reactivar": repo.reactivar_operador,
    },
}


# ------------------------------------------------------------ utilidades

def pausar():
    input("\nPresioná Enter para continuar...")


def pedir(mensaje, validador, *args, valor_actual=None):
    """Pide un dato; con valor_actual, Enter lo conserva."""
    while True:
        texto = input(mensaje)
        if valor_actual is not None and not texto.strip():
            return valor_actual
        try:
            return validador(texto, *args)
        except ValueError as error:
            print(f"Error: {mensaje_error(error)}")


def pedir_id(mensaje):
    while True:
        valor = input(mensaje).strip()
        if valor.isdigit() and int(valor) > 0:
            return int(valor)
        print("Error: ingresá un número entero positivo.")


def pedir_fecha(mensaje, por_defecto=None):
    while True:
        texto = input(mensaje).strip()
        if not texto and por_defecto is not None:
            return por_defecto
        try:
            return datetime.strptime(texto, "%Y-%m-%d").date()
        except ValueError:
            print("Error: usá el formato AAAA-MM-DD.")


def _texto_opcional(valor):
    return valor.strip() or None


def _dinero(valor):
    return formato.dinero(valor)


def _id_usuario_actual():
    sesion = obtener_sesion_actual()
    return sesion["id_usuario"] if sesion else None


def mostrar_tercero(tipo, fila):
    print("-" * 45)
    print(f"ID: {fila[0]} | {fila[1]}")
    print(f"CUIT: {fila[2]} | Email: {fila[3]}")
    print(f"Teléfono: {fila[4] or '-'} | País: {fila[6]}")
    print(f"Dirección: {fila[5] or '-'}")
    if tipo == "OPERADOR":
        print(f"Modalidades: {', '.join(fila[7] or [])}")
    else:
        print(f"Rubro: {fila[7]}")
    estado = fila[8]
    if estado == "INACTIVO" and fila[10]:
        estado += f" (baja {fila[10]:%d/%m/%Y})"
    print(f"Estado: {estado}")


def seleccionar_tercero(tipo, solo_activos=False):
    """Lista y pide un ID. Devuelve la fila o None."""
    filas = _FUNCIONES[tipo]["listar"](not solo_activos)
    if not filas:
        print(f"\nNo hay ningún {NOMBRES[tipo]} registrado.")
        return None

    for fila in filas:
        print(f"  {fila[0]}. {fila[1]} ({fila[8]})")

    id_tercero = pedir_id(f"\nID del {NOMBRES[tipo]}: ")
    fila = next((f for f in filas if f[0] == id_tercero), None)
    if fila is None:
        print("No está en la lista.")
    return fila


def _pedir_extra(tipo, actual=None):
    if tipo == "OPERADOR":
        return pedir(
            f"Modalidades ({', '.join(MEDIOS_TRANSPORTE)}; separadas por coma)"
            + (" [Enter = sin cambios]" if actual else "") + ": ",
            validar_modalidades,
            valor_actual=actual,
        )
    return pedir(
        f"Rubro ({', '.join(RUBROS_PROVEEDOR)})"
        + (" [Enter = sin cambios]" if actual else "") + ": ",
        validar_rubro,
        valor_actual=actual,
    )


def _pedir_datos(tipo, actual=None):
    """Pide los datos de alta o modificación (Enter conserva en modificación)."""
    sufijo = " [Enter = sin cambios]" if actual else ""
    valor = (lambda i: actual[i]) if actual else (lambda i: None)

    datos = {
        "razon_social": pedir(
            f"Razón social{sufijo}: ", validar_largo, "La razón social",
            LARGOS_CONTACTO["razon_social"], valor_actual=valor(1),
        ),
        "cuit": pedir(
            f"CUIT{sufijo}: ", validar_cuit, valor_actual=valor(2)
        ),
        "email": pedir(
            f"Email{sufijo}: ", validar_email_dato, valor_actual=valor(3)
        ),
        "telefono": pedir(
            f"Teléfono (opcional){sufijo}: ", validar_telefono_dato,
            valor_actual=valor(4),
        ),
        "direccion": pedir(
            f"Dirección (opcional){sufijo}: ", validar_largo, "La dirección",
            LARGOS_CONTACTO["direccion"], False, valor_actual=valor(5),
        ),
        "pais": pedir(
            f"País{sufijo}: ", validar_largo, "El país", LARGOS_CONTACTO["pais"],
            valor_actual=valor(6),
        ),
    }
    clave = "modalidades" if tipo == "OPERADOR" else "rubro"
    datos[clave] = _pedir_extra(tipo, valor(7))
    return datos


# ------------------------------------------------------------------ ABM

@requiere_permiso(3)
@solo_internos
def registrar_tercero_service(tipo):
    print(f"\n--- REGISTRAR {NOMBRES[tipo].upper()} ---")
    try:
        datos = _pedir_datos(tipo)
        if _FUNCIONES[tipo]["por_cuit"](datos["cuit"]) is not None:
            print(f"\nYa existe un {NOMBRES[tipo]} con ese CUIT.")
            return
        id_nuevo = _FUNCIONES[tipo]["crear"](datos)
        logger.info("Alta de %s %s", tipo, id_nuevo)
        print(f"\n{NOMBRES[tipo].capitalize()} registrado. ID: {id_nuevo}")
    except Exception as error:
        print(f"\nError al registrar: {mensaje_error(error)}")
    finally:
        pausar()


@requiere_permiso(3)
def listar_terceros_service(tipo):
    print(f"\n--- LISTADO DE {NOMBRES[tipo].upper()}ES ---"
          if tipo == "PROVEEDOR" else "\n--- LISTADO DE OPERADORES LOGÍSTICOS ---")
    try:
        filas = _FUNCIONES[tipo]["listar"](True)
        if not filas:
            print("No hay registros.")
            return
        for fila in filas:
            mostrar_tercero(tipo, fila)
    except Exception as error:
        print(f"Error al listar: {mensaje_error(error)}")
    finally:
        pausar()


@requiere_permiso(3)
def buscar_tercero_service(tipo):
    print(f"\n--- BUSCAR {NOMBRES[tipo].upper()} ---")
    try:
        fila = _FUNCIONES[tipo]["buscar"](pedir_id("ID: "))
        if fila is None:
            print("No existe.")
            return
        mostrar_tercero(tipo, fila)
    except Exception as error:
        print(f"Error al buscar: {mensaje_error(error)}")
    finally:
        pausar()


@requiere_permiso(3)
@solo_internos
def modificar_tercero_service(tipo):
    print(f"\n--- MODIFICAR {NOMBRES[tipo].upper()} ---")
    try:
        actual = _FUNCIONES[tipo]["buscar"](pedir_id("ID: "))
        if actual is None:
            print("No existe.")
            return
        mostrar_tercero(tipo, actual)
        print("\nIngresá los nuevos datos (Enter conserva el valor actual):")
        datos = _pedir_datos(tipo, actual)

        otro = _FUNCIONES[tipo]["por_cuit"](datos["cuit"])
        if otro is not None and otro[0] != actual[0]:
            print(f"\nYa existe otro {NOMBRES[tipo]} con ese CUIT.")
            return

        if _FUNCIONES[tipo]["modificar"](actual[0], datos):
            logger.info("Modificación de %s %s", tipo, actual[0])
            print("\nDatos actualizados.")
        else:
            print("\nNo se pudo modificar.")
    except Exception as error:
        print(f"\nError al modificar: {mensaje_error(error)}")
    finally:
        pausar()


@requiere_permiso(3)
@solo_internos
def baja_tercero_service(tipo):
    print(f"\n--- DAR DE BAJA {NOMBRES[tipo].upper()} (baja lógica) ---")
    try:
        actual = _FUNCIONES[tipo]["buscar"](pedir_id("ID: "))
        if actual is None:
            print("No existe.")
            return
        mostrar_tercero(tipo, actual)
        if actual[8] != "ACTIVO":
            print("\nYa está dado de baja.")
            return

        pendientes = cuentas.listar_facturas_pendientes(tipo, actual[0])
        if pendientes:
            total = sum(f[6] for f in pendientes)
            print(
                f"\nAviso: tiene {len(pendientes)} factura(s) impaga(s) por "
                f"{_dinero(total)}. Se podrán seguir pagando."
            )
        print(
            "La baja impide registrarle facturas nuevas"
            + (" y asignarle tramos." if tipo == "OPERADOR" else ".")
        )
        if input("¿Confirmar baja? (S/N): ").strip().upper() != "S":
            print("Cancelado.")
            return

        if _FUNCIONES[tipo]["baja"](actual[0]):
            logger.info("Baja lógica de %s %s", tipo, actual[0])
            print("\nDado de baja (los datos se conservan).")
        else:
            print("\nNo se pudo dar de baja.")
    except Exception as error:
        print(f"\nError en la baja: {mensaje_error(error)}")
    finally:
        pausar()


@requiere_permiso(3)
@solo_internos
def reactivar_tercero_service(tipo):
    print(f"\n--- REACTIVAR {NOMBRES[tipo].upper()} ---")
    try:
        id_tercero = pedir_id("ID: ")
        if _FUNCIONES[tipo]["reactivar"](id_tercero):
            logger.info("Reactivación de %s %s", tipo, id_tercero)
            print("\nReactivado.")
        else:
            print("\nNo existe o ya estaba activo.")
    except Exception as error:
        print(f"\nError al reactivar: {mensaje_error(error)}")
    finally:
        pausar()


# ------------------------------------------------------- operador: tramos

@requiere_permiso(3)
def tramos_operador_service():
    print("\n--- TRAMOS REALIZADOS POR UN OPERADOR ---")
    try:
        operador = seleccionar_tercero("OPERADOR")
        if operador is None:
            return
        tramos = repo.listar_tramos_operador(operador[0])
        if not tramos:
            print("\nNo tiene tramos asignados.")
            return
        for t in tramos:
            print(
                f"Tramo {t[0]} | Envío {t[1]} ({t[7]}) | {t[2]} | "
                f"{t[3]} -> {t[4]} | Salida {t[5]:%d/%m/%Y} | "
                f"{'Facturado' if t[8] else 'Sin facturar'}"
            )
    except Exception as error:
        print(f"Error: {mensaje_error(error)}")
    finally:
        pausar()


@requiere_permiso(3)
@solo_internos
def asignar_operador_vehiculo_service():
    print("\n--- ASIGNAR OPERADOR A UN VEHÍCULO ---")
    try:
        from app.repositories.vehiculo_repository import (
            listar_vehiculos, buscar_vehiculo_por_id,
        )
        for v in listar_vehiculos():
            print(f"  {v[0]}. {v[1]} {v[2]} | operador: {v[6] or 'sin asignar'}")
        vehiculo = buscar_vehiculo_por_id(pedir_id("\nID del vehículo: "))
        if vehiculo is None:
            print("No existe.")
            return

        operadores = repo.listar_operadores_por_modalidad(vehiculo[1])
        if not operadores:
            print(f"\nNo hay operadores activos con modalidad {vehiculo[1]}.")
            return
        for o in operadores:
            print(f"  {o[0]}. {o[1]}")
        texto = input("ID del operador (0 = quitar operador): ").strip()
        if not texto.isdigit():
            print("Valor inválido.")
            return
        id_operador = int(texto) or None

        repo.asignar_operador_vehiculo(vehiculo[0], id_operador)
        logger.info("Vehículo %s -> operador %s", vehiculo[0], id_operador)
        print("\nVehículo actualizado. Los tramos ya registrados conservan "
              "su operador.")
    except Exception as error:
        print(f"\nError: {mensaje_error(error)}")
    finally:
        pausar()


@requiere_permiso(3)
@solo_internos
def asignar_operador_tramo_service():
    print("\n--- ASIGNAR OPERADOR A UN TRAMO SIN OPERADOR ---")
    try:
        tramos = repo.listar_tramos_sin_operador()
        if not tramos:
            print("Todos los tramos tienen operador.")
            return
        for t in tramos:
            historico = f" | texto histórico: {t[7]}" if t[7] else ""
            print(
                f"  Tramo {t[0]} | Envío {t[1]} | {t[2]} | {t[3]} -> {t[4]} | "
                f"vehículo {t[6]}{historico}"
            )
        id_tramo = pedir_id("\nID del tramo: ")
        tramo = next((t for t in tramos if t[0] == id_tramo), None)
        if tramo is None:
            print("No está en la lista.")
            return

        operadores = repo.listar_operadores_por_modalidad(tramo[2])
        if not operadores:
            print(f"\nNo hay operadores activos con modalidad {tramo[2]}.")
            return
        for o in operadores:
            print(f"  {o[0]}. {o[1]}")
        id_operador = pedir_id("ID del operador: ")

        id_envio = repo.asignar_operador_tramo(id_tramo, id_operador)
        logger.info("Tramo %s -> operador %s", id_tramo, id_operador)
        print("\nOperador asignado.")
        sincronizar_envio_neo4j(id_envio)
    except Exception as error:
        print(f"\nError: {mensaje_error(error)}")
    finally:
        pausar()


# ------------------------------------------------------- cuenta corriente

@requiere_permiso(3)
@solo_internos
def registrar_factura_recibida_service(tipo):
    print(f"\n--- REGISTRAR FACTURA RECIBIDA ({NOMBRES[tipo]}) ---")
    try:
        titular = seleccionar_tercero(tipo, solo_activos=True)
        if titular is None:
            return

        id_tramo = None
        concepto = None
        if tipo == "OPERADOR":
            tramos = cuentas.listar_tramos_facturables(titular[0])
            if not tramos:
                print(
                    "\nEl operador no tiene tramos facturables: solo se "
                    "factura un tramo cuyo envío está Entregado y que no "
                    "tenga factura."
                )
                return
            for t in tramos:
                print(
                    f"  Tramo {t[0]} | Envío {t[1]} | {t[2]} | "
                    f"{t[3]} -> {t[4]} | Salida {t[5]:%d/%m/%Y}"
                )
            id_tramo = pedir_id("ID del tramo facturado: ")
            concepto = input("Detalle (opcional): ").strip() or None
        else:
            concepto = pedir("Concepto: ", texto_obligatorio, "El concepto")

        numero = pedir(
            "Número de comprobante (ej. A-0001-00001234): ",
            texto_obligatorio, "El número de comprobante",
        )
        importe = pedir("Importe total (ARS): ", texto_obligatorio, "El importe")
        hoy = hoy_contable()
        emision = pedir_fecha(
            f"Fecha de emisión AAAA-MM-DD [Enter = {hoy}]: ", hoy
        )
        sugerido = date.fromordinal(emision.toordinal() + DIAS_VENCIMIENTO_DEFECTO)
        vencimiento = pedir_fecha(
            f"Vencimiento AAAA-MM-DD [Enter = {sugerido}, 30 días]: ", sugerido
        )

        id_factura = cuentas.registrar_factura_recibida(
            tipo, titular[0], numero, importe, emision, vencimiento,
            id_tramo=id_tramo, concepto=concepto,
            registrado_por=_id_usuario_actual(),
        )
        logger.info("Factura recibida %s de %s %s", id_factura, tipo, titular[0])
        print(f"\nFactura registrada. ID interno: {id_factura}")
        print("Aumenta lo que le debemos en su cuenta corriente.")
    except Exception as error:
        print(f"\nError al registrar la factura: {mensaje_error(error)}")
    finally:
        pausar()


@requiere_permiso(3)
@solo_internos
def registrar_pago_emitido_service(tipo):
    print(f"\n--- REGISTRAR PAGO A {NOMBRES[tipo].upper()} ---")
    try:
        # Se incluyen inactivos: su deuda se sigue pudiendo pagar.
        titular = seleccionar_tercero(tipo)
        if titular is None:
            return
        pendientes = cuentas.listar_facturas_pendientes(tipo, titular[0])
        if not pendientes:
            print("\nNo tiene facturas pendientes.")
            return
        for f in pendientes:
            print(
                f"  Factura {f[0]} | Comp. {f[1]} | Vence {f[3]:%d/%m/%Y} | "
                f"Total {_dinero(f[4])} | Pendiente {_dinero(f[6])}"
            )
        id_factura = pedir_id("\nID de la factura a pagar: ")
        if id_factura not in {f[0] for f in pendientes}:
            print("No está entre las pendientes de este titular.")
            return
        monto = pedir("Monto (ARS): ", texto_obligatorio, "El monto")
        metodo = pedir("Método de pago: ", texto_obligatorio, "El método")
        referencia = input("Referencia (opcional): ").strip() or None

        id_pago, estado = cuentas.registrar_pago_emitido(
            id_factura, monto, metodo, referencia,
            registrado_por=_id_usuario_actual(),
        )
        logger.info("Pago emitido %s a factura recibida %s", id_pago, id_factura)
        print(f"\nPago registrado. ID: {id_pago}. Estado de la factura: {estado}")
    except Exception as error:
        print(f"\nError al registrar el pago: {mensaje_error(error)}")
    finally:
        pausar()


@requiere_permiso(3)
def consultar_cuenta_tercero_service(tipo):
    print(f"\n--- CUENTA CORRIENTE ({NOMBRES[tipo]}) ---")
    try:
        titular = seleccionar_tercero(tipo)
        if titular is None:
            return
        cuenta = cuentas.consultar_cuenta_tercero(tipo, titular[0])
        print(f"\n{titular[1]}")
        if cuenta is None:
            print("Todavía no tiene movimientos. Saldo: $0,00")
            return
        print(f"Facturas recibidas: {cuenta['cantidad_facturas']} | "
              f"Facturado: {_dinero(cuenta['facturado'])}")
        print(f"Pagado por nosotros: {_dinero(cuenta['pagado'])}")
        print(f"SALDO (lo que le debemos): {_dinero(cuenta['saldo'])} "
              f"{cuenta['moneda']}")

        pendientes = cuentas.listar_facturas_pendientes(tipo, titular[0])
        if pendientes:
            print("\nFacturas pendientes:")
            hoy = hoy_contable()
            for f in pendientes:
                marca = " VENCIDA" if f[3] < hoy else ""
                origen = f"tramo {f[8]}" if f[8] else (f[9] or "")
                print(
                    f"  {f[0]} | Comp. {f[1]} | Emisión {f[2]:%d/%m/%Y} | "
                    f"Vence {f[3]:%d/%m/%Y}{marca} | Total {_dinero(f[4])} | "
                    f"Pendiente {_dinero(f[6])} | {f[7]} | {origen}"
                )
    except Exception as error:
        print(f"Error al consultar: {mensaje_error(error)}")
    finally:
        pausar()


@requiere_permiso(3)
def movimientos_tercero_service(tipo):
    print(f"\n--- MOVIMIENTOS DE CUENTA ({NOMBRES[tipo]}) ---")
    try:
        titular = seleccionar_tercero(tipo)
        if titular is None:
            return
        movimientos = cuentas.listar_movimientos_tercero(tipo, titular[0])
        if not movimientos:
            print("Sin movimientos.")
            return
        acumulado = 0
        for fecha, tipo_mov, importe, referencia, detalle in movimientos:
            acumulado += importe
            print(
                f"{fecha:%d/%m/%Y} | {_dinero(importe):>15} | saldo {_dinero(acumulado):>15} | "
                f"{formato.descripcion_movimiento(tipo_mov, referencia, detalle)}"
            )
    except Exception as error:
        print(f"Error: {mensaje_error(error)}")
    finally:
        pausar()


@requiere_permiso(3)
def vencimientos_service():
    print("\n--- FACTURAS RECIBIDAS VENCIDAS O POR VENCER ---")
    try:
        texto = input("Mostrar las que vencen en los próximos N días [Enter = 7]: ")
        dias = int(texto) if texto.strip().isdigit() else 7
        filas = cuentas.listar_vencimientos(dias)
        if not filas:
            print("\nNo hay facturas vencidas ni por vencer en ese plazo.")
            return
        total = 0
        for f in filas:
            total += f[8]
            situacion = (
                f"VENCIDA hace {-f[6]} día(s)" if f[6] < 0
                else "vence HOY" if f[6] == 0
                else f"vence en {f[6]} día(s)"
            )
            print(
                f"{f[5]:%d/%m/%Y} | {situacion:<20} | {f[1]:<9} | {f[2]} | "
                f"Comp. {f[3]} | Pendiente {_dinero(f[8])} | {f[9]}"
            )
        print(f"\nTotal pendiente en el listado: {_dinero(total)}")
    except Exception as error:
        print(f"Error: {mensaje_error(error)}")
    finally:
        pausar()
