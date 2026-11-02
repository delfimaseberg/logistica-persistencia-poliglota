"""Validaciones puras de proveedores, operadores logísticos y sus cuentas.

No acceden a bases de datos, para poder probarlas de forma aislada.
"""

import re
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from app.utils.validaciones_logistica import MEDIOS_TRANSPORTE, normalizar


ZONA_CONTABLE = ZoneInfo("America/Argentina/Buenos_Aires")
MONEDA_TERCEROS = "ARS"
DIAS_VENCIMIENTO_DEFECTO = 30

ESTADOS_TERCERO = ("ACTIVO", "INACTIVO")
RUBROS_PROVEEDOR = (
    "CONTENEDORES", "SENSORES", "SEGUROS", "MANTENIMIENTO", "OTROS"
)
TIPOS_TITULAR = ("PROVEEDOR", "OPERADOR")

_PESOS_CUIT = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)


def hoy_contable():
    return datetime.now(ZONA_CONTABLE).date()


def validar_cuit(valor):
    """Acepta 11 dígitos con o sin guiones y devuelve XX-XXXXXXXX-X.

    Verifica el dígito verificador con el algoritmo de AFIP.
    """
    texto = str(valor or "").strip()
    digitos = re.sub(r"[-\s]", "", texto)

    if not re.fullmatch(r"[0-9]{11}", digitos):
        raise ValueError("El CUIT debe tener 11 dígitos (formato XX-XXXXXXXX-X).")

    suma = sum(int(d) * p for d, p in zip(digitos[:10], _PESOS_CUIT))
    resto = 11 - (suma % 11)
    verificador = 0 if resto == 11 else 9 if resto == 10 else resto

    if verificador != int(digitos[10]):
        raise ValueError("El CUIT no es válido (dígito verificador incorrecto).")

    return f"{digitos[:2]}-{digitos[2:10]}-{digitos[10]}"


def validar_modalidades(valores):
    """Normaliza una lista de medios (Terrestre, Marítimo, Aéreo) sin repetir."""
    if isinstance(valores, str):
        valores = [v for v in re.split(r"[,/]", valores)]

    resultado = []
    for valor in valores or []:
        if not str(valor).strip():
            continue
        coincidencia = next(
            (m for m in MEDIOS_TRANSPORTE
             if normalizar(m) == normalizar(str(valor))),
            None,
        )
        if coincidencia is None:
            raise ValueError(
                "Modalidad inválida: "
                f"{valor}. Usá: {', '.join(MEDIOS_TRANSPORTE)}."
            )
        if coincidencia not in resultado:
            resultado.append(coincidencia)

    if not resultado:
        raise ValueError("Indicá al menos una modalidad.")

    return resultado


def validar_rubro(valor):
    texto = str(valor or "").strip().upper()
    if texto not in RUBROS_PROVEEDOR:
        raise ValueError(
            f"El rubro debe ser uno de: {', '.join(RUBROS_PROVEEDOR)}."
        )
    return texto


def validar_tipo_titular(tipo):
    texto = str(tipo or "").strip().upper()
    if texto not in TIPOS_TITULAR:
        raise ValueError("El titular debe ser PROVEEDOR u OPERADOR.")
    return texto


def importe_positivo(valor, mensaje):
    """Decimal con 2 decimales y mayor a cero (igual que en clientes)."""
    try:
        importe = Decimal(str(valor))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(mensaje)
    if not importe.is_finite():
        raise ValueError(mensaje)
    importe = importe.quantize(Decimal("0.01"))
    if importe <= 0:
        raise ValueError(mensaje)
    from app.utils.validaciones_datos import controlar_maximo
    return controlar_maximo(importe)


def validar_numero_comprobante(valor):
    texto = str(valor or "").strip().upper()
    if not texto:
        raise ValueError("Falta el número de comprobante.")
    if len(texto) > 30:
        raise ValueError("El número de comprobante no puede superar 30 caracteres.")
    return texto


def validar_fechas_factura(fecha_emision, fecha_vencimiento=None, hoy=None):
    """Devuelve (emisión, vencimiento).

    La emisión no puede ser futura. Sin vencimiento, se usan 30 días desde la
    emisión. El vencimiento no puede ser anterior a la emisión.
    """
    hoy = hoy or hoy_contable()

    if not isinstance(fecha_emision, date) or isinstance(fecha_emision, datetime):
        raise ValueError("La fecha de emisión debe ser una fecha calendario.")
    if fecha_emision > hoy:
        raise ValueError("La fecha de emisión no puede ser futura.")

    if fecha_vencimiento is None:
        fecha_vencimiento = fecha_emision + timedelta(days=DIAS_VENCIMIENTO_DEFECTO)
    elif (
        not isinstance(fecha_vencimiento, date)
        or isinstance(fecha_vencimiento, datetime)
    ):
        raise ValueError("La fecha de vencimiento debe ser una fecha calendario.")

    if fecha_vencimiento < fecha_emision:
        raise ValueError("El vencimiento no puede ser anterior a la emisión.")

    return fecha_emision, fecha_vencimiento


def validar_origen_factura(tipo_titular, id_tramo, concepto):
    """Operador: tramo obligatorio. Proveedor: sin tramo y con concepto."""
    tipo_titular = validar_tipo_titular(tipo_titular)
    concepto = str(concepto or "").strip() or None

    if concepto is not None and len(concepto) > 255:
        raise ValueError("El concepto no puede superar 255 caracteres.")

    if tipo_titular == "OPERADOR":
        if id_tramo is None:
            raise ValueError(
                "La factura de un operador debe indicar el tramo que realizó."
            )
        return int(id_tramo), concepto

    if id_tramo is not None:
        raise ValueError("La factura de un proveedor no se asocia a un tramo.")
    if concepto is None:
        raise ValueError("La factura de un proveedor debe indicar su concepto.")
    return None, concepto


def envio_entregado(estado):
    return normalizar(str(estado or "")) == "entregado"


def validar_partes_usuario(id_cliente=None, id_proveedor=None, id_operador=None):
    """Un usuario pertenece como mucho a una parte; ninguna = interno."""
    partes = [p for p in (id_cliente, id_proveedor, id_operador) if p is not None]
    if len(partes) > 1:
        raise ValueError(
            "Un usuario puede pertenecer a un solo cliente, proveedor u operador."
        )
    return id_cliente, id_proveedor, id_operador


def describir_parte(id_cliente=None, id_proveedor=None, id_operador=None,
                    nombre_parte=None):
    """Texto para listados: 'Cliente: X', 'Proveedor: Y', 'Operador: Z' o 'Interno'."""
    if id_cliente is not None:
        etiqueta, ident = "Cliente", id_cliente
    elif id_proveedor is not None:
        etiqueta, ident = "Proveedor", id_proveedor
    elif id_operador is not None:
        etiqueta, ident = "Operador", id_operador
    else:
        return "Interno"

    if nombre_parte:
        return f"{etiqueta}: {nombre_parte}"
    return f"{etiqueta} ID {ident}"
