"""Validaciones puras para los procesos financieros periódicos.

Este módulo no consulta repositorios ni realiza escrituras. La moneda, el
tratamiento impositivo y la evidencia de apertura deben llegar configurados
explícitamente; nunca se completan con valores predeterminados.
"""

from datetime import date, datetime
from decimal import Decimal, InvalidOperation


class FinanzasNoConfiguradas(ValueError):
    """La operación no dispone de datos financieros aprobados suficientes."""


def _decimal_finito(valor, nombre):
    if valor is None:
        raise FinanzasNoConfiguradas(f"Falta {nombre}.")

    try:
        importe = Decimal(str(valor))
    except (InvalidOperation, ValueError, TypeError):
        raise FinanzasNoConfiguradas(f"{nombre} no es un importe válido.")

    if not importe.is_finite():
        raise FinanzasNoConfiguradas(f"{nombre} debe ser finito.")
    return importe


def validar_tarifa_aprobada(
    tarifa, moneda_cuenta, configuracion_fiscal, fecha_emision
):
    """Valida que una tarifa esté completa para una eventual factura.

    No calcula impuestos ni deriva el total de la tarifa: esos valores deben
    venir informados y aprobados por la configuración comercial/fiscal.
    """
    if not tarifa:
        raise FinanzasNoConfiguradas("El envío no tiene una tarifa registrada.")

    if str(tarifa.get("estado", "")).strip().upper() != "APROBADA":
        raise FinanzasNoConfiguradas("La tarifa del envío no está aprobada.")

    if not moneda_cuenta:
        raise FinanzasNoConfiguradas(
            "La moneda de la cuenta corriente todavía no está configurada."
        )

    moneda_tarifa = str(tarifa.get("moneda", "")).strip().upper()
    moneda_configurada = str(moneda_cuenta).strip().upper()
    if len(moneda_configurada) != 3 or not moneda_configurada.isalpha():
        raise FinanzasNoConfiguradas(
            "La moneda de la cuenta debe configurarse explícitamente."
        )
    if len(moneda_tarifa) != 3 or not moneda_tarifa.isalpha():
        raise FinanzasNoConfiguradas("La tarifa no tiene moneda configurada.")
    if moneda_tarifa != moneda_configurada:
        raise FinanzasNoConfiguradas(
            "La moneda de la tarifa no coincide con la de la cuenta."
        )

    if not configuracion_fiscal or not configuracion_fiscal.get("aprobada"):
        raise FinanzasNoConfiguradas(
            "No existe una configuración fiscal aprobada para la tarifa."
        )
    if not configuracion_fiscal.get("activa"):
        raise FinanzasNoConfiguradas(
            "La configuración fiscal de la tarifa no está activa."
        )
    if not isinstance(fecha_emision, date):
        raise FinanzasNoConfiguradas(
            "La fecha de emisión contable debe estar definida."
        )
    vigente_desde = configuracion_fiscal.get("vigente_desde")
    vigente_hasta = configuracion_fiscal.get("vigente_hasta")
    if not isinstance(vigente_desde, date):
        raise FinanzasNoConfiguradas(
            "La configuración fiscal no tiene inicio de vigencia."
        )
    if fecha_emision < vigente_desde or (
        vigente_hasta is not None
        and (not isinstance(vigente_hasta, date) or fecha_emision > vigente_hasta)
    ):
        raise FinanzasNoConfiguradas(
            "La configuración fiscal no está vigente en la fecha de emisión."
        )
    if not configuracion_fiscal.get("id_configuracion_fiscal"):
        raise FinanzasNoConfiguradas(
            "La configuración fiscal no tiene identificador auditable."
        )
    if (
        not str(configuracion_fiscal.get("codigo", "")).strip()
        or not configuracion_fiscal.get("version")
        or not str(configuracion_fiscal.get("referencia_aprobacion", "")).strip()
        or not configuracion_fiscal.get("aprobado_por")
    ):
        raise FinanzasNoConfiguradas(
            "La configuración fiscal carece de versión o aprobación documentada."
        )
    fecha_configuracion = configuracion_fiscal.get("aprobado_en")
    if not isinstance(fecha_configuracion, datetime) or fecha_configuracion.tzinfo is None:
        raise FinanzasNoConfiguradas(
            "La aprobación fiscal debe tener una fecha con zona horaria."
        )
    if tarifa.get("id_configuracion_fiscal") != configuracion_fiscal.get(
        "id_configuracion_fiscal"
    ):
        raise FinanzasNoConfiguradas(
            "La tarifa no referencia la configuración fiscal validada."
        )

    if not str(tarifa.get("referencia_aprobacion", "")).strip():
        raise FinanzasNoConfiguradas(
            "Falta la referencia de aprobación de la tarifa."
        )
    fecha_aprobacion = tarifa.get("aprobado_en")
    if (
        not tarifa.get("aprobado_por")
        or not isinstance(fecha_aprobacion, datetime)
        or fecha_aprobacion.tzinfo is None
    ):
        raise FinanzasNoConfiguradas(
            "Faltan los datos con zona horaria de quién y cuándo aprobó la tarifa."
        )
    if not str(tarifa.get("tratamiento_impositivo", "")).strip():
        raise FinanzasNoConfiguradas(
            "Falta el tratamiento impositivo aprobado para la tarifa."
        )
    if tarifa["tratamiento_impositivo"] != configuracion_fiscal.get("tratamiento"):
        raise FinanzasNoConfiguradas(
            "El tratamiento impositivo de la tarifa no coincide con su perfil."
        )

    tasa_tarifa = tarifa.get("tasa_impositiva")
    tasa_configuracion = configuracion_fiscal.get("tasa")
    if (tasa_tarifa is None) != (tasa_configuracion is None):
        raise FinanzasNoConfiguradas(
            "La tasa impositiva de la tarifa no coincide con su perfil."
        )
    if tasa_tarifa is not None and _decimal_finito(
        tasa_tarifa, "la tasa impositiva"
    ) != _decimal_finito(tasa_configuracion, "la tasa fiscal configurada"):
        raise FinanzasNoConfiguradas(
            "La tasa impositiva de la tarifa no coincide con su perfil."
        )

    base = _decimal_finito(tarifa.get("importe_base"), "el importe base")
    impuestos = _decimal_finito(
        tarifa.get("importe_impuestos"), "el importe de impuestos"
    )
    total = _decimal_finito(tarifa.get("importe_total"), "el importe total")

    if base < 0 or impuestos < 0:
        raise FinanzasNoConfiguradas(
            "Los importes base e impositivo no pueden ser negativos en una tarifa."
        )
    if total <= 0:
        raise FinanzasNoConfiguradas(
            "El importe total aprobado debe ser mayor a cero."
        )

    # No se compara base + impuestos con total: todavía no está decidido si
    # el importe aprobado expresa impuestos incluidos o adicionados.
    return {
        "importe_base": base,
        "importe_impuestos": impuestos,
        "importe_total": total,
        "moneda": moneda_tarifa,
    }


def validar_evento_entrega(
    id_envio,
    evento,
    estado_postgres,
    sincronizacion_pendiente=False,
    cantidad_eventos_entrega=1,
):
    """Exige una única evidencia Mongo válida y concordancia con PostgreSQL."""
    if sincronizacion_pendiente:
        raise FinanzasNoConfiguradas(
            "Hay una actualización de estado pendiente para el envío."
        )

    if not evento or str(evento.get("tipo", "")).strip().upper() != "ENTREGADO":
        raise FinanzasNoConfiguradas(
            "No hay un evento de entrega válido registrado para el envío."
        )

    if cantidad_eventos_entrega != 1:
        raise FinanzasNoConfiguradas(
            "Debe existir exactamente un evento ENTREGADO para el envío."
        )

    try:
        mismo_envio = int(evento.get("envio_id")) == int(id_envio)
    except (TypeError, ValueError):
        mismo_envio = False
    if not mismo_envio:
        raise FinanzasNoConfiguradas(
            "El evento ENTREGADO no corresponde al envío candidato."
        )

    if not evento.get("_id"):
        raise FinanzasNoConfiguradas(
            "El evento ENTREGADO no tiene identificador auditable."
        )

    fecha_evento = evento.get("fecha_hora")
    if not isinstance(fecha_evento, datetime) or fecha_evento.tzinfo is None:
        raise FinanzasNoConfiguradas(
            "La fecha del evento ENTREGADO debe incluir zona horaria."
        )

    if str(estado_postgres or "").strip().casefold() != "entregado".casefold():
        raise FinanzasNoConfiguradas(
            "El estado del envío no coincide con el evento de entrega."
        )

    return {
        "evento_id": str(evento["_id"]),
        "fecha_hora": fecha_evento,
    }


def validar_factura_original_no_duplicada(
    existe_factura_envio=False,
    existe_factura_evento=False,
):
    """Bloquea reintentos que ya tengan factura original por envío o evento."""
    if existe_factura_envio or existe_factura_evento:
        raise FinanzasNoConfiguradas(
            "Ya existe una factura original para el envío o evento de entrega."
        )


def validar_correccion_factura(id_factura_original, correccion, moneda_original):
    """Exige que una corrección quede enlazada, aprobada y en igual moneda."""
    if not correccion:
        raise FinanzasNoConfiguradas("Faltan los datos de la corrección.")
    if correccion.get("id_factura_original") != id_factura_original:
        raise FinanzasNoConfiguradas(
            "La corrección no referencia la factura original indicada."
        )
    if str(correccion.get("tipo", "")).strip().upper() not in {
        "CREDITO", "DEBITO"
    }:
        raise FinanzasNoConfiguradas("El tipo de corrección no es válido.")
    if not str(correccion.get("motivo", "")).strip():
        raise FinanzasNoConfiguradas("La corrección requiere un motivo.")
    if not str(correccion.get("referencia_aprobacion", "")).strip():
        raise FinanzasNoConfiguradas(
            "La corrección requiere una aprobación documentada."
        )
    if not correccion.get("aprobado_por"):
        raise FinanzasNoConfiguradas("Falta quién aprobó la corrección.")
    fecha_aprobacion = correccion.get("aprobada_en")
    if not isinstance(fecha_aprobacion, datetime) or fecha_aprobacion.tzinfo is None:
        raise FinanzasNoConfiguradas(
            "La aprobación de la corrección requiere fecha con zona horaria."
        )
    if not str(correccion.get("idempotency_key", "")).strip():
        raise FinanzasNoConfiguradas(
            "La corrección requiere una clave idempotente."
        )

    moneda = str(correccion.get("moneda", "")).strip().upper()
    if not moneda_original or moneda != str(moneda_original).strip().upper():
        raise FinanzasNoConfiguradas(
            "La moneda de la corrección no coincide con la factura original."
        )

    importe = _decimal_finito(correccion.get("importe"), "el importe corregido")
    if importe <= 0:
        raise FinanzasNoConfiguradas(
            "El importe de una corrección debe ser mayor a cero."
        )
    base = _decimal_finito(
        correccion.get("importe_base"), "el importe base corregido"
    )
    impuestos = _decimal_finito(
        correccion.get("importe_impuestos"),
        "el importe de impuestos corregido",
    )
    if base < 0 or impuestos < 0:
        raise FinanzasNoConfiguradas(
            "Los componentes de una corrección no pueden ser negativos."
        )
    if (
        not correccion.get("id_configuracion_fiscal")
        or not str(correccion.get("tratamiento_impositivo", "")).strip()
    ):
        raise FinanzasNoConfiguradas(
            "Falta el snapshot fiscal de la corrección."
        )
    return importe


def validar_apertura_verificada(apertura, moneda_cuenta):
    """Exige evidencia y aprobación explícitas; cero solo vale si está probado."""
    if not apertura:
        raise FinanzasNoConfiguradas(
            "No hay una apertura de cuenta corriente verificada."
        )

    referencia = str(apertura.get("referencia_fuente", "")).strip()
    aprobador = apertura.get("aprobado_por")
    aprobado_en = apertura.get("aprobado_en")
    if not referencia or not aprobador or not isinstance(aprobado_en, datetime):
        raise FinanzasNoConfiguradas(
            "La apertura carece de referencia o aprobación documentada."
        )
    if aprobado_en.tzinfo is None:
        raise FinanzasNoConfiguradas(
            "La fecha de aprobación debe incluir zona horaria."
        )
    if not apertura.get("fecha_vigencia"):
        raise FinanzasNoConfiguradas(
            "Falta la fecha desde la que rige el saldo inicial documentado."
        )

    moneda = str(apertura.get("moneda", "")).strip().upper()
    configurada = str(moneda_cuenta or "").strip().upper()
    if not configurada:
        raise FinanzasNoConfiguradas(
            "La moneda de la cuenta corriente todavía no está configurada."
        )
    if moneda != configurada:
        raise FinanzasNoConfiguradas(
            "La moneda de la apertura no coincide con la de la cuenta."
        )

    return {
        "saldo_inicial": _decimal_finito(
            apertura.get("saldo_inicial"), "el saldo inicial"
        ),
        "moneda": moneda,
        "referencia_fuente": referencia,
    }


def validar_conciliacion_saldo(
    saldo_actual,
    saldo_reconstruido,
    aprobacion_ajuste=None,
):
    """Bloquea diferencias no justificadas o no aprobadas documentalmente."""
    actual = _decimal_finito(saldo_actual, "el saldo actual")
    reconstruido = _decimal_finito(saldo_reconstruido, "el saldo reconstruido")
    diferencia = actual - reconstruido

    if diferencia != 0:
        if not aprobacion_ajuste or not str(
            aprobacion_ajuste.get("referencia", "")
        ).strip() or not aprobacion_ajuste.get("aprobado_por"):
            raise FinanzasNoConfiguradas(
                "La diferencia de conciliación requiere aprobación documentada."
            )
        fecha_aprobacion = aprobacion_ajuste.get("aprobado_en")
        if not isinstance(fecha_aprobacion, datetime) or fecha_aprobacion.tzinfo is None:
            raise FinanzasNoConfiguradas(
                "La aprobación del ajuste debe incluir fecha con zona horaria."
            )

    return diferencia


def validar_periodo_movimiento_tardio(
    periodo_contable, periodo_abierto, periodo_origen
):
    """Evita reabrir silenciosamente el período de origen de un movimiento."""
    for nombre, periodo in (
        ("período contable", periodo_contable),
        ("período abierto", periodo_abierto),
        ("período de origen", periodo_origen),
    ):
        if not isinstance(periodo, date) or periodo.day != 1:
            raise FinanzasNoConfiguradas(
                f"El {nombre} debe ser el primer día del mes."
            )

    if periodo_contable != periodo_abierto:
        raise FinanzasNoConfiguradas(
            "El movimiento tardío debe registrarse en el período abierto."
        )
    if periodo_contable <= periodo_origen:
        raise FinanzasNoConfiguradas(
            "El movimiento tardío no puede reabrir su período de origen."
        )
