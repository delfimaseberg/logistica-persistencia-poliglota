"""Formato argentino para pantallas y archivos.

Importes $1.500,00 · decimales con coma (66,7 %) · fechas dd/mm/aaaa (hh:mm)
en hora argentina.
"""

from datetime import date, datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo


ZONA = ZoneInfo("America/Argentina/Buenos_Aires")


def numero(valor, decimales=2):
    """1234567.891 -> '1.234.567,89'. None -> '-'."""
    if valor is None:
        return "-"
    texto = f"{float(valor) if not isinstance(valor, Decimal) else valor:,.{decimales}f}"
    return texto.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def compacto(valor, maximo_decimales=2):
    """Sin ceros de más: 20.00 -> '20', 4.18 -> '4,18', -32.597321 -> '-32,6' (1 decimal)."""
    if valor is None:
        return "-"
    texto = f"{float(valor):.{maximo_decimales}f}".rstrip("0").rstrip(".")
    if texto in ("-0", ""):
        texto = "0"
    return texto.replace(".", ",")


def entero(valor):
    return numero(valor, 0)


def dinero(valor):
    """$1.500,00 (negativos: -$1.500,00)."""
    if valor is None:
        return "-"
    signo = "-" if valor < 0 else ""
    return f"{signo}${numero(abs(valor), 2)}"


def porcentaje(valor, decimales=1):
    """66.7 -> '66,7 %'."""
    return "-" if valor is None else f"{numero(valor, decimales)} %"


def _local(valor):
    if valor.tzinfo is None:
        valor = valor.replace(tzinfo=timezone.utc)
    return valor.astimezone(ZONA)


def fecha(valor):
    """dd/mm/aaaa. Acepta date, datetime o texto ISO."""
    if valor is None or valor == "":
        return "-"
    if isinstance(valor, str):
        try:
            valor = datetime.fromisoformat(valor)
        except ValueError:
            return valor
    if isinstance(valor, datetime):
        valor = _local(valor)
    return valor.strftime("%d/%m/%Y")


def fecha_hora(valor):
    """dd/mm/aaaa hh:mm en hora argentina. Acepta datetime, date o texto ISO."""
    if valor is None or valor == "":
        return "-"
    if isinstance(valor, str):
        try:
            valor = datetime.fromisoformat(valor)
        except ValueError:
            return valor
    if isinstance(valor, datetime):
        return _local(valor).strftime("%d/%m/%Y %H:%M")
    if isinstance(valor, date):
        return valor.strftime("%d/%m/%Y")
    return str(valor)


# Nombres para mostrar de códigos internos.
TIPOS_EVENTO = {
    "CARGA_INICIADA": "Carga iniciada",
    "EN_TRANSITO": "En tránsito",
    "ADUANA": "Aduana",
    "DESCARGA": "Descarga",
    "RETRASO": "Retraso",
    "ENTREGADO": "Entregado",
    "CANCELADO": "Cancelado",
}
TIPOS_MOVIMIENTO = {
    "FACTURA": "Factura",
    "PAGO": "Pago",
    "FACTURA_RECIBIDA": "Factura recibida",
    "PAGO_EMITIDO": "Pago emitido",
    "AJUSTE": "Ajuste",
    "SALDO_INICIAL": "Saldo inicial",
}


def _datos_documentales(referencia_documental):
    """'envio=13;regla=1;envio_manual' -> ({'envio': '13', 'regla': '1'}, {'envio_manual'})."""
    datos, marcas = {}, set()
    for parte in str(referencia_documental or "").split(";"):
        parte = parte.strip()
        if "=" in parte:
            clave, valor = parte.split("=", 1)
            datos[clave.strip()] = valor.strip()
        elif parte:
            marcas.add(parte)
    return datos, marcas


def descripcion_movimiento(tipo_origen, referencia_origen, referencia_documental):
    """Texto legible de un movimiento de cuenta corriente (clientes o terceros)."""
    datos, marcas = _datos_documentales(referencia_documental)
    tipo = str(tipo_origen or "")
    if tipo == "FACTURA":
        texto = f"Factura N.º {referencia_origen}"
        if "envio" in datos:
            texto += f" del envío {datos['envio']}"
            if "envio_automatica" in marcas:
                texto += " (automática)"
        elif "reporte" in datos:
            texto += f" del reporte {datos['reporte']}"
        elif "factura_manual" in marcas:
            texto += " (histórica)"
        return texto
    if tipo == "PAGO":
        texto = f"Pago N.º {referencia_origen}"
        if "factura" in datos:
            texto += f" de la factura N.º {datos['factura']}"
        return texto + (f" ({datos['metodo'].lower()})" if datos.get("metodo") else "")
    if tipo == "FACTURA_RECIBIDA":
        return "Factura recibida" + (f" {datos['comprobante']}" if datos.get("comprobante") else "")
    if tipo == "PAGO_EMITIDO":
        return "Pago emitido" + (f" ({datos['metodo'].lower()})" if datos.get("metodo") else "")
    return movimiento(tipo)


def mes(texto):
    """'2026-10' -> '10/2026'."""
    texto = str(texto)
    if len(texto) == 7 and texto[4] == "-":
        return f"{texto[5:]}/{texto[:4]}"
    return texto


def evento(codigo):
    return TIPOS_EVENTO.get(str(codigo), str(codigo).replace("_", " ").capitalize())


def movimiento(codigo):
    return TIPOS_MOVIMIENTO.get(str(codigo), str(codigo).replace("_", " ").capitalize())
