"""Cálculo conservador y registro de cierres mensuales de cuenta corriente."""

from datetime import date
from decimal import Decimal, InvalidOperation
import logging
from zoneinfo import ZoneInfo

from app.repositories import cierre_cuenta_repository
from app.utils.validaciones_financieras import (
    FinanzasNoConfiguradas,
    validar_apertura_verificada,
)

logger = logging.getLogger(__name__)


class CierreBloqueado(ValueError):
    """El cliente no reúne evidencia suficiente para cerrar el período."""


class CierreDuplicado(ValueError):
    """El snapshot del cliente y período ya existe y es inmutable."""


def _dinero(value, nombre):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise CierreBloqueado(f"{nombre} no es un importe válido.")
    if not result.is_finite():
        raise CierreBloqueado(f"{nombre} no es un importe finito.")
    return result.quantize(Decimal("0.01"))


def _mes(fecha):
    if isinstance(fecha, date):
        return fecha.replace(day=1)
    raise CierreBloqueado("El período debe ser una fecha correspondiente al inicio del mes.")


def _mes_pago(fecha):
    # PostgreSQL devuelve TIMESTAMPTZ como datetime aware; la fecha contable
    # se determina en el calendario acordado para el proyecto.
    if not hasattr(fecha, "tzinfo") or fecha.tzinfo is None:
        raise CierreBloqueado("Un pago carece de fecha con zona horaria verificable.")
    return fecha.astimezone(ZoneInfo("America/Argentina/Buenos_Aires")).date().replace(day=1)


def _fecha_local(fecha, nombre):
    if not hasattr(fecha, "tzinfo") or fecha.tzinfo is None:
        raise CierreBloqueado(f"{nombre} carece de fecha con zona horaria verificable.")
    return fecha.astimezone(ZoneInfo("America/Argentina/Buenos_Aires")).date()


def calcular_snapshot_cierre(datos, periodo):
    """Valida conciliación de cuenta/ledger y produce un snapshot sin escribir."""
    periodo = _mes(periodo)
    cuenta = datos.get("cuenta")
    if not cuenta:
        raise CierreBloqueado("El cliente no tiene cuenta corriente.")
    moneda = str(cuenta.get("moneda") or "").strip().upper()
    if len(moneda) != 3 or not moneda.isalpha():
        raise CierreBloqueado("La moneda de la cuenta no está configurada explícitamente.")

    try:
        apertura = validar_apertura_verificada(datos.get("apertura"), moneda)
    except FinanzasNoConfiguradas as error:
        raise CierreBloqueado(str(error)) from error
    apertura_row = datos["apertura"]
    inicio = apertura_row["fecha_vigencia"]
    if inicio > periodo:
        raise CierreBloqueado("La apertura verificada todavía no rige al inicio del período.")
    if periodo < inicio.replace(day=1):
        raise CierreBloqueado("No se puede cerrar un período anterior a la apertura verificada.")

    movimientos = datos.get("movimientos", [])
    por_origen = {}
    for move in movimientos:
        if move["moneda"] != moneda:
            raise CierreBloqueado("Hay movimientos en una moneda distinta a la cuenta.")
        key = (move["tipo_origen"], str(move["referencia_origen"]), move["tipo_movimiento"])
        if key in por_origen:
            raise CierreBloqueado("El ledger contiene movimientos duplicados para un documento.")
        por_origen[key] = move

    matched_keys = set()

    def require_move(kind, identifier, move_type, expected, source_period, docname):
        key = (kind, str(identifier), move_type)
        move = por_origen.get(key)
        if move is None:
            raise CierreBloqueado(f"{docname} {identifier} no tiene movimiento conciliado en el ledger.")
        if _dinero(move["importe_firmado"], "Importe del ledger") != expected:
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
    for invoice in datos.get("facturas", []):
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

    for payment in datos.get("pagos", []):
        # Aún no hay esquema de reversos; todos los pagos persistidos se tratan
        # como activos, y la ausencia de un ledger coincidente bloquea.
        pay_date = _fecha_local(payment["fecha"], f"El pago {payment['id_pago']}")
        if pay_date < inicio:
            continue
        if str(payment.get("moneda") or "").strip().upper() != moneda:
            raise CierreBloqueado(
                f"La moneda del pago {payment['id_pago']} falta o no coincide con la cuenta."
            )
        expected = -_dinero(payment["monto"], "Importe del pago")
        require_move("PAGO", payment["id_pago"], "PAGO", expected,
                     _mes_pago(payment["fecha"]), "Pago")

    for correction in datos.get("correcciones", []):
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
        signed = -amount if kind == "CREDITO" else amount
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
        if move["fecha_contable"] >= inicio and key not in matched_keys:
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
        if source_period and source_period < posted_period:
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
    for invoice in datos.get("facturas", []):
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
    opening = apertura["saldo_inicial"] + sum((
        _dinero(m["importe_firmado"], "Importe de movimiento")
        for m in movimientos
        if inicio <= m["fecha_contable"] < periodo and m["tipo_movimiento"] != "APERTURA"
    ), Decimal("0"))
    current_period_moves = [m for m in movimientos if periodo <= m["fecha_contable"] < next_month
                            and m["tipo_movimiento"] != "APERTURA"]
    reconstructed = apertura["saldo_inicial"] + sum((
        _dinero(m["importe_firmado"], "Importe de movimiento")
        for m in movimientos
        if inicio <= m["fecha_contable"] and m["tipo_movimiento"] != "APERTURA"
    ), Decimal("0"))
    if _dinero(cuenta["saldo"], "Saldo actual") != reconstructed:
        raise CierreBloqueado(
            "El saldo actual no concilia con la apertura y el ledger; se requiere conciliación aprobada y trazable."
        )

    total_facturas = sum((_dinero(m["importe_firmado"], "Factura") for m in current_period_moves
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

    final = opening + total_facturas - total_pagos + ajustes
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


def cerrar_cuenta_mensual(id_cliente, periodo):
    periodo = _mes(periodo)
    try:
        result = cierre_cuenta_repository.ejecutar_cierre_atomico(
            id_cliente, periodo,
            lambda datos: calcular_snapshot_cierre(datos, periodo),
        )
        logger.info("Cierre mensual creado: cliente=%s período=%s", id_cliente, periodo)
        return {"estado": "CERRADO", **result}
    except cierre_cuenta_repository.CierreExistente as error:
        logger.warning("Cierre duplicado bloqueado: cliente=%s período=%s", id_cliente, periodo)
        raise CierreDuplicado(str(error)) from error
    except CierreBloqueado as error:
        logger.warning("Cierre bloqueado: cliente=%s período=%s motivo=%s", id_cliente, periodo, error)
        return {"estado": "BLOQUEADO", "motivo": str(error)}
    except Exception:
        logger.exception("Error al cerrar cuenta: cliente=%s período=%s", id_cliente, periodo)
        raise
