"""Cálculo conservador y registro de cierres mensuales de cuenta corriente."""

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from app.utils.logger import obtener_logger
from zoneinfo import ZoneInfo

from app.repositories import cierre_cuenta_repository
from app.utils.validaciones_financieras import (
    FinanzasNoConfiguradas,
    validar_apertura_verificada,
)
from app.utils.errores import mensaje_error
from app.utils import formato
from app.utils.validaciones_datos import IMPORTE_MAXIMO

# Al archivo logs/app.log (no a la consola, para no ensuciar los menús).
logger = obtener_logger("cierre_cuenta")


class CierreBloqueado(ValueError):  # el mes no se puede cerrar porque algo no concilia
    """El cliente no reúne evidencia suficiente para cerrar el período."""


class CierreDuplicado(ValueError):  # ese mes ya estaba cerrado para el cliente
    """El snapshot del cliente y período ya existe y es inmutable."""


def _dinero(value, nombre):  # pasa un importe a Decimal con centavos; lo usa todo el cálculo del cierre
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise CierreBloqueado(f"{nombre} no es un importe válido.")
    if not result.is_finite():
        raise CierreBloqueado(f"{nombre} no es un importe finito.")
    return result.quantize(Decimal("0.01"))


def _mes(fecha):  # lleva una fecha al día 1 de su mes; lo usan el cierre y la previsualización
    if isinstance(fecha, date):
        return fecha.replace(day=1)
    raise CierreBloqueado("El período debe ser una fecha correspondiente al inicio del mes.")


def _mes_pago(fecha):  # mes contable de un pago, en hora argentina; lo usa calcular_snapshot_cierre
    # PostgreSQL devuelve TIMESTAMPTZ como datetime aware; la fecha contable
    # se determina en el calendario acordado para el proyecto.
    if not hasattr(fecha, "tzinfo") or fecha.tzinfo is None:
        raise CierreBloqueado("Un pago carece de fecha con zona horaria verificable.")
    return fecha.astimezone(ZoneInfo("America/Argentina/Buenos_Aires")).date().replace(day=1)


def _fecha_local(fecha, nombre):  # día en hora argentina de un pago o corrección; lo usa calcular_snapshot_cierre
    if not hasattr(fecha, "tzinfo") or fecha.tzinfo is None:
        raise CierreBloqueado(f"{nombre} carece de fecha con zona horaria verificable.")
    return fecha.astimezone(ZoneInfo("America/Argentina/Buenos_Aires")).date()


def calcular_snapshot_cierre(datos, periodo):  # controla que todo concilie y calcula los saldos del mes sin guardar; la usan el cierre y la previsualización de apertura
    """Valida conciliación de cuenta/ledger y produce un snapshot sin escribir."""
    periodo = _mes(periodo)
    cuenta = datos.get("cuenta")
    if not cuenta:
        raise CierreBloqueado("El cliente no tiene cuenta corriente.")
    moneda = str(cuenta.get("moneda") or "").strip().upper()
    if len(moneda) != 3 or not moneda.isalpha():
        raise CierreBloqueado("La moneda de la cuenta no está configurada explícitamente.")

    try:
        apertura = validar_apertura_verificada(datos.get("apertura"), moneda)  # sin apertura aprobada no se puede cerrar
    except FinanzasNoConfiguradas as error:
        raise CierreBloqueado(str(error)) from error
    apertura_row = datos["apertura"]
    inicio = apertura_row["fecha_vigencia"]
    # El primer período puede ser parcial: si la apertura rige a mitad de
    # mes, ese mes se cierra con saldo inicial = saldo de la apertura y solo
    # suma los movimientos desde la fecha de vigencia.
    if periodo < inicio.replace(day=1):  # no se cierra nada anterior a la apertura
        raise CierreBloqueado("No se puede cerrar un período anterior a la apertura verificada.")

    movimientos = datos.get("movimientos", [])
    por_origen = {}
    for move in movimientos:
        if move["moneda"] != moneda:
            raise CierreBloqueado("Hay movimientos en una moneda distinta a la cuenta.")
        key = (move["tipo_origen"], str(move["referencia_origen"]), move["tipo_movimiento"])
        if key in por_origen:  # un mismo documento no puede tener dos movimientos
            raise CierreBloqueado("El ledger contiene movimientos duplicados para un documento.")
        por_origen[key] = move

    matched_keys = set()

    def require_move(kind, identifier, move_type, expected, source_period, docname):  # busca el movimiento de un documento y controla importe y período
        key = (kind, str(identifier), move_type)
        move = por_origen.get(key)
        if move is None:
            raise CierreBloqueado(f"{docname} {identifier} no tiene movimiento conciliado en el ledger.")
        if _dinero(move["importe_firmado"], "Importe del ledger") != expected:  # el movimiento tiene que tener el mismo importe que el documento
            raise CierreBloqueado(f"El importe del ledger no coincide con {docname} {identifier}.")
        posted_period = move["fecha_contable"].replace(day=1)
        if posted_period == source_period and move["periodo_origen"] not in (None, source_period):
            raise CierreBloqueado(f"El período de origen de {docname} {identifier} no coincide.")
        if posted_period != source_period and move["periodo_origen"] != source_period:
            raise CierreBloqueado(f"El movimiento tardío de {docname} {identifier} no conserva su período de origen.")
        if move["fecha_contable"] < inicio:
            raise CierreBloqueado(f"{docname} {identifier} está contabilizado antes de la apertura.")
        matched_keys.add(key)
        return move

    # Todo documento posterior a la apertura debe estar representado en ledger.
    for invoice in datos.get("facturas", []):  # cada factura desde la apertura tiene que tener su movimiento
        issue_date = invoice["fecha_emision"]
        if issue_date < inicio:
            continue
        if str(invoice.get("moneda") or "").strip().upper() != moneda:
            raise CierreBloqueado(
                f"La moneda de la factura {invoice['id_factura']} falta o no coincide con la cuenta."
            )
        amount = _dinero(invoice["total"], "Total de factura")
        if str(invoice["estado"]).strip().casefold() == "anulada":
            # Solo se puede cerrar si existe crédito aprobado y contabilizado
            # por el total. La comprobación agregada se realiza más abajo.
            pass
        require_move("FACTURA", invoice["id_factura"], "FACTURA", amount,
                     issue_date.replace(day=1), "Factura")

    for payment in datos.get("pagos", []):  # lo mismo con los pagos
        # Aún no hay esquema de reversos; todos los pagos persistidos se tratan
        # como activos, y la ausencia de un ledger coincidente bloquea.
        pay_date = _fecha_local(payment["fecha"], f"El pago {payment['id_pago']}")
        if pay_date < inicio:
            continue
        if str(payment.get("moneda") or "").strip().upper() != moneda:
            raise CierreBloqueado(
                f"La moneda del pago {payment['id_pago']} falta o no coincide con la cuenta."
            )
        expected = -_dinero(payment["monto"], "Importe del pago")  # el pago se registra en negativo
        require_move("PAGO", payment["id_pago"], "PAGO", expected,
                     _mes_pago(payment["fecha"]), "Pago")

    for correction in datos.get("correcciones", []):  # y con las correcciones, que necesitan aprobación
        correction_date = _fecha_local(
            correction["registrada_en"], f"La corrección {correction['id_correccion']}"
        )
        if correction_date < inicio:
            continue
        if str(correction.get("moneda") or "").strip().upper() != moneda:
            raise CierreBloqueado(
                f"La moneda de la corrección {correction['id_correccion']} falta o no coincide con la cuenta."
            )
        if not correction["referencia_aprobacion"] or not correction["aprobado_por"]:
            raise CierreBloqueado("Hay una corrección sin aprobación documentada.")
        amount = _dinero(correction["importe"], "Importe de corrección")
        kind = str(correction["tipo"]).upper()
        if kind not in {"CREDITO", "DEBITO"}:
            raise CierreBloqueado("La corrección tiene un tipo no reconocido.")
        signed = -amount if kind == "CREDITO" else amount  # el crédito baja la deuda y el débito la sube
        move_type = kind
        require_move("CORRECCION", correction["id_correccion"], move_type,
                     signed, correction["fecha_emision_original"].replace(day=1), "Corrección")

    # Rechazar tipos ajenos a documentos aprobados: 003 no guarda aprobación
    # de ajustes ni reversos, por lo que no se pueden incluir con seguridad.
    for move in movimientos:
        if move["tipo_movimiento"] == "APERTURA" and move["tipo_origen"] == "APERTURA":
            continue
        if move["tipo_movimiento"] in {"FACTURA", "PAGO", "CREDITO", "DEBITO"}:
            continue
        else:
            raise CierreBloqueado(
                f"El movimiento {move['id_movimiento']} ({move['tipo_movimiento']}) no tiene aprobación verificable en el esquema."
            )

    for move in movimientos:
        if move["tipo_movimiento"] == "APERTURA" and move["tipo_origen"] == "APERTURA":
            continue
        key = (move["tipo_origen"], str(move["referencia_origen"]), move["tipo_movimiento"])
        if move["fecha_contable"] >= inicio and key not in matched_keys:  # un movimiento sin documento que lo respalde bloquea el cierre
            raise CierreBloqueado(
                f"El movimiento {move['id_movimiento']} no corresponde a una factura, pago o corrección conciliada."
            )

    # Los movimientos tardíos necesitan un período de origen y solo se aceptan
    # en el primer período abierto siguiente. Si el dato no basta para probarlo,
    # se bloquea en vez de reubicarlo implícitamente.
    cerrados = set(datos.get("periodos_cerrados", []))
    for move in movimientos:
        if move["tipo_movimiento"] == "APERTURA":
            continue
        if move["fecha_contable"] > periodo:
            continue
        source_period = move["periodo_origen"]
        posted_period = move["fecha_contable"].replace(day=1)
        if source_period and source_period < posted_period:  # movimiento tardío: va al primer mes abierto después de su mes de origen
            if source_period not in cerrados:
                raise CierreBloqueado("Un movimiento tardío refiere a un período de origen que no está cerrado.")
            siguiente_abierto = date(source_period.year, source_period.month, 1)
            while siguiente_abierto in cerrados:
                siguiente_abierto = date(
                    siguiente_abierto.year + (siguiente_abierto.month == 12),
                    1 if siguiente_abierto.month == 12 else siguiente_abierto.month + 1,
                    1,
                )
            if posted_period != siguiente_abierto:
                raise CierreBloqueado("El movimiento tardío debe registrarse en el período abierto que se está cerrando.")

    next_month = date(periodo.year + (periodo.month == 12), 1 if periodo.month == 12 else periodo.month + 1, 1)

    # Facturas anuladas requieren crédito íntegro. Pago de factura anulada no
    # se puede revertir porque no existe entidad/estado de reverso de pago.
    for invoice in datos.get("facturas", []):  # una factura anulada necesita un crédito por el total y no puede tener pagos
        if str(invoice["estado"]).strip().casefold() != "anulada" or invoice["fecha_emision"] < inicio:
            continue
        credits = sum((_dinero(c["importe"], "Crédito") for c in datos.get("correcciones", [])
                       if c["id_factura_original"] == invoice["id_factura"]
                       and str(c["tipo"]).upper() == "CREDITO"
                       and _fecha_local(c["registrada_en"], "La corrección") < next_month), Decimal("0"))
        if credits != _dinero(invoice["total"], "Total de factura"):
            raise CierreBloqueado(f"La factura anulada {invoice['id_factura']} no tiene crédito íntegro aprobado.")
        if any(p["id_factura"] == invoice["id_factura"] for p in datos.get("pagos", [])):
            raise CierreBloqueado(f"La factura anulada {invoice['id_factura']} tiene pagos sin flujo de reverso.")

    # Sumar movimientos contabilizados desde la apertura hasta el fin del mes.
    # El saldo inicial del mes se reconstruye desde la apertura verificada y
    # todos los movimientos anteriores al primer día del período.
    opening = apertura["saldo_inicial"] + sum((  # saldo inicial del mes: apertura más todo lo anterior al mes
        _dinero(m["importe_firmado"], "Importe de movimiento")
        for m in movimientos
        if inicio <= m["fecha_contable"] < periodo and m["tipo_movimiento"] != "APERTURA"
    ), Decimal("0"))
    current_period_moves = [m for m in movimientos if periodo <= m["fecha_contable"] < next_month
                            and m["tipo_movimiento"] != "APERTURA"]
    reconstructed = apertura["saldo_inicial"] + sum((  # saldo de hoy rearmado con todos los movimientos
        _dinero(m["importe_firmado"], "Importe de movimiento")
        for m in movimientos
        if inicio <= m["fecha_contable"] and m["tipo_movimiento"] != "APERTURA"
    ), Decimal("0"))
    if _dinero(cuenta["saldo"], "Saldo actual") != reconstructed:  # si el saldo de la cuenta no coincide con los movimientos, no se cierra
        raise CierreBloqueado(
            "El saldo actual no concilia con la apertura y el ledger; se requiere conciliación aprobada y trazable."
        )

    total_facturas = sum((_dinero(m["importe_firmado"], "Factura") for m in current_period_moves  # totales del mes por tipo de movimiento
                          if m["tipo_movimiento"] == "FACTURA"), Decimal("0"))
    total_pagos = -sum((_dinero(m["importe_firmado"], "Pago") for m in current_period_moves
                        if m["tipo_movimiento"] == "PAGO"), Decimal("0"))
    ajustes = sum((_dinero(m["importe_firmado"], "Ajuste") for m in current_period_moves
                   if m["tipo_movimiento"] in {"CREDITO", "DEBITO"}), Decimal("0"))
    # Chequeo adicional evita sumar un documento cuyo movimiento no pudo
    # mapearse, sin confundir movimientos de apertura con cargos.
    known = {"APERTURA", "FACTURA", "PAGO", "CREDITO", "DEBITO"}
    if any(m["tipo_movimiento"] not in known for m in current_period_moves):
        raise CierreBloqueado("Hay movimientos del período sin clasificación conciliable.")

    final = opening + total_facturas - total_pagos + ajustes  # saldo final del mes
    return {
        "moneda": moneda,
        "saldo_inicial": opening,
        "total_facturas": total_facturas,
        "total_pagos": total_pagos,
        "ajustes_netos": ajustes,
        "saldo_final": final,
        "referencia_saldo_inicial": apertura["referencia_fuente"],
        "id_apertura": apertura_row["id_apertura"],
    }


def hoy_argentina():  # fecha de hoy en Argentina; la usan el cierre y la apertura
    return datetime.now(ZoneInfo("America/Argentina/Buenos_Aires")).date()


def siguiente_mes(periodo):  # día 1 del mes siguiente; la usa cerrar_cuenta_mensual
    return date(periodo.year + (periodo.month == 12),
                1 if periodo.month == 12 else periodo.month + 1, 1)


def cerrar_cuenta_mensual(id_cliente, periodo, hoy=None):  # cierra un mes de un cliente; la usa cerrar_mes_todos
    periodo = _mes(periodo)
    hoy = hoy or hoy_argentina()
    # Un cierre es inmutable: si el mes no terminó, un movimiento posterior
    # del mismo mes quedaría fuera del snapshot.
    if siguiente_mes(periodo) > hoy:  # solo se cierran meses ya terminados
        motivo = f"El período {periodo:%Y-%m} todavía no terminó."
        logger.warning("Cierre bloqueado: cliente=%s período=%s motivo=%s",
                       id_cliente, periodo, motivo)
        return {"estado": "BLOQUEADO", "motivo": motivo}
    try:
        result = cierre_cuenta_repository.ejecutar_cierre_atomico(  # en una transacción: bloquea la cuenta, calcula y guarda el cierre
            id_cliente, periodo,
            lambda datos: calcular_snapshot_cierre(datos, periodo),
        )
        logger.info("Cierre mensual creado: cliente=%s período=%s", id_cliente, periodo)
        return {"estado": "CERRADO", **result}  # el mes queda CERRADO y ya no se puede cambiar
    except cierre_cuenta_repository.CierreExistente as error:
        logger.warning("Cierre duplicado bloqueado: cliente=%s período=%s", id_cliente, periodo)
        raise CierreDuplicado(str(error)) from error  # ese mes ya estaba cerrado: no se cierra dos veces
    except CierreBloqueado as error:
        logger.warning("Cierre bloqueado: cliente=%s período=%s motivo=%s", id_cliente, periodo, error)
        return {"estado": "BLOQUEADO", "motivo": str(error)}
    except Exception:
        logger.exception("Error al cerrar cuenta: cliente=%s período=%s", id_cliente, periodo)
        raise


def cerrar_mes_todos(periodo, hoy=None):  # cierra un mes para todos los clientes; la usa "Cierre mensual" (facturación, opción 11)
    """Cierra el período para todos los clientes con cuenta corriente.

    Devuelve {"periodo", "cerrados", "bloqueados", "ya_cerrados", "errores"}.
    Cada cliente se cierra en su propia transacción.
    """
    periodo = _mes(periodo)
    resumen = {"periodo": periodo, "cerrados": [], "bloqueados": [],
               "ya_cerrados": [], "errores": []}

    for id_cliente, nombre in cierre_cuenta_repository.listar_clientes_con_cuenta():  # si un cliente falla, se sigue con los demás
        try:
            resultado = cerrar_cuenta_mensual(id_cliente, periodo, hoy=hoy)
        except CierreDuplicado as error:
            resumen["ya_cerrados"].append(
                {"id_cliente": id_cliente, "cliente": nombre, "motivo": str(error)}
            )
            continue
        except Exception as error:
            resumen["errores"].append(
                {"id_cliente": id_cliente, "cliente": nombre, "error": mensaje_error(error)}
            )
            continue

        if resultado["estado"] == "CERRADO":
            resumen["cerrados"].append({"id_cliente": id_cliente, "cliente": nombre,
                                        **resultado})
        else:
            resumen["bloqueados"].append({"id_cliente": id_cliente, "cliente": nombre,
                                          "motivo": resultado["motivo"]})

    logger.info(
        "Cierre %s: cerrados=%s bloqueados=%s ya_cerrados=%s errores=%s",
        periodo, len(resumen["cerrados"]), len(resumen["bloqueados"]),
        len(resumen["ya_cerrados"]), len(resumen["errores"]),
    )
    return resumen


# ------------------------------------------------------------------
# Apertura de cuenta corriente
# ------------------------------------------------------------------

def validar_datos_apertura(saldo_inicial, fecha_vigencia, referencia, hoy=None):  # controla saldo, fecha y referencia de una apertura; la usan la previsualización y el registro
    hoy = hoy or hoy_argentina()
    saldo = _dinero(saldo_inicial, "El saldo inicial")
    if abs(saldo) > IMPORTE_MAXIMO:
        raise CierreBloqueado(
            f"El saldo inicial no puede superar {formato.dinero(IMPORTE_MAXIMO)}.")
    if not isinstance(fecha_vigencia, date) or isinstance(fecha_vigencia, datetime):
        raise CierreBloqueado("La fecha de vigencia debe ser una fecha calendario.")
    if fecha_vigencia > hoy:  # la apertura no puede regir desde el futuro
        raise CierreBloqueado("La fecha de vigencia no puede ser futura.")
    referencia = str(referencia or "").strip()
    if not referencia:
        raise CierreBloqueado("La apertura requiere una referencia documentada.")
    return saldo, fecha_vigencia, referencia


def previsualizar_apertura(id_cliente, saldo_inicial, fecha_vigencia, hoy=None):  # prueba la apertura sin guardarla; la usa "Apertura de cuenta corriente" (facturación, opción 10)
    """Sin escribir: con esta apertura, ¿el primer mes concilia y cerraría?

    Devuelve {"concilia": bool, "motivo" o "snapshot", "saldo_documentos"}.
    """
    saldo, fecha_vigencia, _ = validar_datos_apertura(
        saldo_inicial, fecha_vigencia, "previsualización", hoy=hoy
    )
    facturado, pagado, sugerido = cierre_cuenta_repository.calcular_saldo_documentos(
        id_cliente, fecha_vigencia
    )
    datos = cierre_cuenta_repository.leer_datos_cierre(id_cliente)
    cuenta = datos.get("cuenta") or {}
    datos["apertura"] = {  # apertura de prueba, sin aprobar todavía
        "id_apertura": None,
        "id_cliente": id_cliente,
        "moneda": cuenta.get("moneda"),
        "saldo_inicial": saldo,
        "fecha_vigencia": fecha_vigencia,
        "referencia_fuente": "previsualización",
        "aprobado_por": -1,
        "aprobado_en": datetime.now(ZoneInfo("UTC")),
    }
    resultado = {
        "saldo_documentos": {"facturado": facturado, "pagado": pagado,
                             "saldo": sugerido},
    }
    try:
        resultado["snapshot"] = calcular_snapshot_cierre(  # simula el cierre del primer mes
            datos, fecha_vigencia.replace(day=1)
        )
        resultado["concilia"] = True
    except CierreBloqueado as error:
        resultado["concilia"] = False
        resultado["motivo"] = str(error)
    return resultado


def registrar_apertura(id_cliente, saldo_inicial, fecha_vigencia, referencia,  # guarda la apertura aprobada; la usa la opción 10 de facturación
                       aprobado_por, hoy=None):
    saldo, fecha_vigencia, referencia = validar_datos_apertura(
        saldo_inicial, fecha_vigencia, referencia, hoy=hoy
    )
    id_apertura = cierre_cuenta_repository.registrar_apertura(
        id_cliente, saldo, fecha_vigencia, referencia, aprobado_por
    )
    logger.info("Apertura %s registrada: cliente=%s saldo=%s vigencia=%s",
                id_apertura, id_cliente, saldo, fecha_vigencia)
    return id_apertura
