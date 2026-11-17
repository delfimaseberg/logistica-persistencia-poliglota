"""Cálculo determinista de componentes tarifarios, sin acceso a bases."""

from decimal import Decimal, InvalidOperation


class CalculoTarifaInvalido(ValueError):  # error cuando faltan datos o las reglas no cierran
    """Los datos o las reglas no permiten calcular un importe completo."""


def _decimal(valor, nombre, *, positivo=False):  # pasa un valor a Decimal o corta el cálculo
    try:
        numero = Decimal(str(valor))
    except (InvalidOperation, TypeError, ValueError):
        raise CalculoTarifaInvalido(f"Falta o no es válido {nombre}.")
    if not numero.is_finite() or (positivo and numero <= 0):
        raise CalculoTarifaInvalido(f"Falta o no es válido {nombre}.")
    return numero


def calcular_componentes(cargas, tramos, componentes):  # suma los componentes de una regla para un envío, sin IVA; la usa cotizar (cotizacion_envio)
    """Devuelve el subtotal comercial y su detalle; no calcula impuestos.

    Las reglas configuradas son aditivas. Una regla repetida que coincida con
    el mismo ámbito y dimensión se considera ambigua y bloquea el cálculo.
    """
    cargas = list(cargas or [])
    tramos = list(tramos or [])
    componentes = list(componentes or [])
    validar_estructura_componentes(componentes)
    bases = [c for c in componentes if c.get("criterio") == "BASE"]
    if len(bases) != 1:  # tiene que haber un solo cargo base
        raise CalculoTarifaInvalido(
            "La versión debe tener exactamente un componente base."
        )

    peso_total = Decimal("0")
    if any(c.get("criterio") in {"PESO", "PESO_DISTANCIA", "CATEGORIA", "FRAGIL"} for c in componentes):  # el peso solo se exige si alguna regla lo usa
        if not cargas:
            raise CalculoTarifaInvalido("El envío no tiene partidas de carga.")
        peso_total = sum(
            (_decimal(x.get("peso_kg"), "el peso real de una partida", positivo=True)
             for x in cargas), Decimal("0")
        )

    distancia_total = Decimal("0")
    if any(c.get("criterio") in {"DISTANCIA", "PESO_DISTANCIA"} for c in componentes):  # igual con la distancia de los tramos
        if not tramos:
            raise CalculoTarifaInvalido("El envío no tiene tramos registrados.")
        distancias = [
            _decimal(t.get("distancia_km"), f"la distancia del tramo {t.get('id_tramo', '')}", positivo=True)
            for t in tramos
        ]
        distancia_total = sum(distancias, Decimal("0"))
    if any(c.get("criterio") == "TRANSPORTE" for c in componentes):
        if not tramos:
            raise CalculoTarifaInvalido("El envío no tiene tramos registrados.")

    detalle = []
    aplicados = set()

    def agregar(componente, referencia, cantidad):  # suma una línea de detalle: importe unitario por cantidad
        key = (
            componente.get("criterio"), componente.get("ambito"),
            str(referencia), componente.get("base_calculo"),
        )
        if key in aplicados:  # la misma regla dos veces sobre lo mismo es ambigua
            raise CalculoTarifaInvalido(
                f"Hay reglas tarifarias incompatibles para {key[0]} ({key[2]})."
            )
        aplicados.add(key)
        importe_unitario = _decimal(componente.get("importe"), "el importe de una regla")
        parcial = importe_unitario * cantidad  # importe de la línea
        detalle.append({
            "id_componente": componente.get("id_componente"),
            "criterio": componente["criterio"],
            "selector": componente.get("selector"),
            "referencia": str(referencia),
            "base_calculo": componente["base_calculo"],
            "cantidad": cantidad,
            "importe_unitario": importe_unitario,
            "importe": parcial,
        })

    for componente in componentes:  # cada criterio se aplica al envío, a cada partida o a cada tramo
        criterio = componente.get("criterio")
        ambito = componente.get("ambito")
        base = componente.get("base_calculo")
        selector = componente.get("selector")
        importe = _decimal(componente.get("importe"), "el importe de una regla")
        if importe < 0:
            raise CalculoTarifaInvalido("El importe de una regla no puede ser negativo.")

        if criterio == "BASE":
            if ambito != "ENVIO" or base != "FIJO" or selector not in (None, ""):
                raise CalculoTarifaInvalido("La regla base debe ser fija por envío y sin selector.")
            agregar(componente, "envio", Decimal("1"))
        elif criterio == "PESO":
            if ambito != "ENVIO" or base != "POR_KG":
                raise CalculoTarifaInvalido("La regla de peso debe aplicarse por kg al envío.")
            agregar(componente, "envio", peso_total)
        elif criterio == "DISTANCIA":
            if ambito != "ENVIO" or base != "POR_KM":
                raise CalculoTarifaInvalido("La regla de distancia debe aplicarse por km al envío.")
            agregar(componente, "envio", distancia_total)
        elif criterio == "PESO_DISTANCIA":
            if ambito != "ENVIO" or base != "POR_KG_KM":
                raise CalculoTarifaInvalido("La regla peso-distancia debe aplicarse por kg-km al envío.")
            agregar(componente, "envio", peso_total * distancia_total)
        elif criterio in {"CATEGORIA", "FRAGIL"}:
            if ambito != "PARTIDA" or base not in {"FIJO", "POR_KG"}:
                raise CalculoTarifaInvalido(f"La regla {criterio.lower()} debe aplicarse por partida.")
            for index, carga in enumerate(cargas):
                coincide = (
                    str(carga.get("tipo_carga", "")).strip().casefold()
                    == str(selector or "").strip().casefold()
                    if criterio == "CATEGORIA"
                    else bool(carga.get("fragil")) and str(selector or "true").casefold() == "true"
                )
                if coincide:
                    peso = _decimal(carga.get("peso_kg"), "el peso real de una partida", positivo=True)
                    agregar(componente, carga.get("id_envio_carga", index), peso if base == "POR_KG" else Decimal("1"))
        elif criterio == "TRANSPORTE":  # una línea por cada tramo del medio de la regla
            if ambito != "TRAMO" or base not in {"FIJO", "POR_KM"}:
                raise CalculoTarifaInvalido("La regla de transporte debe aplicarse por tramo.")
            for index, tramo in enumerate(tramos):
                if str(tramo.get("medio_transporte", "")).strip().casefold() == str(selector or "").strip().casefold():
                    cantidad = Decimal("1") if base == "FIJO" else _decimal(
                        tramo.get("distancia_km"), f"la distancia del tramo {tramo.get('id_tramo', '')}", positivo=True
                    )
                    agregar(componente, tramo.get("id_tramo", index), cantidad)
        else:
            raise CalculoTarifaInvalido(f"Criterio tarifario desconocido: {criterio!r}.")

    total = sum((item["importe"] for item in detalle), Decimal("0"))  # total sin IVA
    # tarifa_envio usa NUMERIC(14,2); impedir que PostgreSQL redondee en
    # silencio hasta que la empresa apruebe una política de redondeo.
    if total != total.quantize(Decimal("0.01")):  # no se redondea a escondidas
        raise CalculoTarifaInvalido(
            "El resultado requiere redondeo a centavos; falta definir la política de redondeo."
        )
    return {"importe_base": total, "detalle": detalle}


def validar_estructura_componentes(componentes):  # controla la forma de una regla; la usan crear y aprobar regla y calcular_componentes
    """Valida la forma de una regla sin inventar entradas ni importes."""
    bases = [c for c in componentes if c.get("criterio") == "BASE"]
    if len(bases) != 1:
        raise CalculoTarifaInvalido("La regla debe tener exactamente un componente base.")
    permitidas = {  # combinaciones válidas de criterio, ámbito y base
        ("BASE", "ENVIO", "FIJO"),
        ("PESO", "ENVIO", "POR_KG"),
        ("DISTANCIA", "ENVIO", "POR_KM"),
        ("PESO_DISTANCIA", "ENVIO", "POR_KG_KM"),
        ("CATEGORIA", "PARTIDA", "FIJO"),
        ("CATEGORIA", "PARTIDA", "POR_KG"),
        ("FRAGIL", "PARTIDA", "FIJO"),
        ("FRAGIL", "PARTIDA", "POR_KG"),
        ("TRANSPORTE", "TRAMO", "FIJO"),
        ("TRANSPORTE", "TRAMO", "POR_KM"),
    }
    vistos = set()
    for c in componentes:
        key = (c.get("criterio"), c.get("ambito"), c.get("base_calculo"))
        if key not in permitidas:
            raise CalculoTarifaInvalido(f"Combinación de regla no compatible: {key}.")
        selector = c.get("selector")
        if c["criterio"] in {"CATEGORIA", "TRANSPORTE"} and not str(selector or "").strip():
            raise CalculoTarifaInvalido(f"El componente {c['criterio']} requiere selector.")
        if c["criterio"] == "FRAGIL" and str(selector or "true").strip().casefold() != "true":
            raise CalculoTarifaInvalido("El componente FRAGIL requiere el selector true.")
        if c["criterio"] in {"BASE", "PESO", "DISTANCIA", "PESO_DISTANCIA"} and selector:
            raise CalculoTarifaInvalido(f"El componente {c['criterio']} no admite selector.")
        identity = (c.get("criterio"), str(selector or "").casefold(), c.get("ambito"))
        if identity in vistos:  # no puede haber dos componentes iguales
            raise CalculoTarifaInvalido(
                f"Hay componentes duplicados/incompatibles para {identity[0]} {identity[1]} "
                "en el mismo ámbito; no se aplica prioridad ni acumulación implícita."
            )
        vistos.add(identity)
        amount = _decimal(c.get("importe"), "el importe de una regla")
        if amount < 0:
            raise CalculoTarifaInvalido("El importe de una regla no puede ser negativo.")
