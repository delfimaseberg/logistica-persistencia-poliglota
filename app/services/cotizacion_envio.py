"""Cotización de un envío con la tarifa estándar (cálculo puro, sin bases).

La tarifa estándar es una regla del motor existente (regla_tarifaria_version)
con código TARIFA_ESTANDAR y solo dos tipos de componentes:
- BASE fijo por envío;
- TRANSPORTE fijo por tramo, uno por medio (Terrestre, Marítimo, Aéreo).

Al neto se le suma IVA fijo del 21 %. Moneda: ARS.
"""

from decimal import Decimal, ROUND_HALF_UP

from app.services.tarifas_calculo import CalculoTarifaInvalido, calcular_componentes


CODIGO_TARIFA = "TARIFA_ESTANDAR"  # código de la regla con la que se facturan los envíos
MONEDA = "ARS"
TASA_IVA = Decimal("0.21")  # IVA fijo del 21 por ciento
TRATAMIENTO_IVA = "IVA_21"
CENTAVO = Decimal("0.01")  # los importes se redondean a centavos


class CotizacionImposible(ValueError):  # error cuando no se puede calcular el importe; la facturación automática lo usa para omitir el envío
    """El envío o la tarifa no permiten calcular un importe completo."""


def calcular_iva(neto):  # IVA del neto redondeado a centavos; lo usan cotizar y la factura de reportes
    """IVA 21 % redondeado a centavos (mitad hacia arriba)."""
    return (Decimal(neto) * TASA_IVA).quantize(CENTAVO, rounding=ROUND_HALF_UP)


def validar_regla_estandar(componentes):  # controla que la tarifa solo tenga cargo base y precio fijo por tramo; la usa cotizar
    """La tarifa estándar solo admite BASE fijo y TRANSPORTE fijo por tramo."""
    for componente in componentes:
        tipo = (
            componente.get("criterio"),
            componente.get("ambito"),
            componente.get("base_calculo"),
        )
        if tipo not in {("BASE", "ENVIO", "FIJO"), ("TRANSPORTE", "TRAMO", "FIJO")}:
            raise CotizacionImposible(
                "La tarifa estándar solo admite cargo base por envío y precio "
                f"fijo por tramo; tiene un componente {tipo[0]}."
            )


def cotizar(tramos, componentes):  # calcula líneas, neto, IVA y total de un envío; la usan cotizar_envio y emitir_factura_envio
    """Devuelve líneas, neto, IVA y total para los tramos de un envío.

    tramos: dicts con id_tramo, medio_transporte, origen y destino.
    componentes: los de la versión aprobada de TARIFA_ESTANDAR.
    """
    tramos = list(tramos or [])
    componentes = list(componentes or [])

    if not tramos:  # sin tramos no hay nada que cobrar
        raise CotizacionImposible("El envío no tiene tramos registrados.")
    if not componentes:
        raise CotizacionImposible("No hay una tarifa estándar aprobada.")

    validar_regla_estandar(componentes)

    precios = {
        str(c.get("selector") or "").strip().casefold()
        for c in componentes if c.get("criterio") == "TRANSPORTE"
    }
    sin_precio = sorted({  # medios de los tramos que no tienen precio en la tarifa
        t["medio_transporte"] for t in tramos
        if str(t.get("medio_transporte") or "").strip().casefold() not in precios
    })
    if sin_precio:  # si falta el precio de algún medio, no se factura a medias
        raise CotizacionImposible(
            "No hay precio definido para el medio: " + ", ".join(sin_precio) + "."
        )

    try:
        calculo = calcular_componentes([], tramos, componentes)  # suma base y tramos con el motor de reglas tarifarias
    except CalculoTarifaInvalido as error:
        raise CotizacionImposible(str(error)) from error

    por_tramo = {str(t["id_tramo"]): t for t in tramos}
    lineas = []
    for item in calculo["detalle"]:
        importe = item["importe"].quantize(CENTAVO)
        if item["criterio"] == "BASE":  # línea del cargo base; las demás son una por tramo
            lineas.append({
                "concepto": "BASE",
                "id_tramo": None,
                "medio_transporte": None,
                "descripcion": "Cargo base por envío",
                "importe": importe,
            })
        else:
            tramo = por_tramo[item["referencia"]]
            lineas.append({
                "concepto": "TRAMO",
                "id_tramo": tramo["id_tramo"],
                "medio_transporte": tramo["medio_transporte"],
                "descripcion": (
                    f"Tramo {tramo['id_tramo']} {tramo['medio_transporte']}: "
                    f"{tramo.get('origen', '')} -> {tramo.get('destino', '')}"
                )[:255],
                "importe": importe,
            })

    # Base primero y luego los tramos en el orden del recorrido.
    orden = {str(t["id_tramo"]): i for i, t in enumerate(tramos)}
    lineas.sort(key=lambda l: (
        l["concepto"] != "BASE", orden.get(str(l["id_tramo"]), -1)
    ))
    for numero, linea in enumerate(lineas, start=1):
        linea["linea"] = numero

    neto = sum((l["importe"] for l in lineas), Decimal("0")).quantize(CENTAVO)  # neto: suma de todas las líneas
    if neto <= 0:
        raise CotizacionImposible("El importe calculado debe ser mayor a cero.")
    iva = calcular_iva(neto)  # el total que se factura es neto + IVA

    return {
        "lineas": lineas,
        "neto": neto,
        "iva": iva,
        "total": neto + iva,
        "tasa_iva": TASA_IVA,
        "tratamiento": TRATAMIENTO_IVA,
        "moneda": MONEDA,
    }
