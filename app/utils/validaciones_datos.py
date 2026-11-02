"""Validaciones comunes de altas y modificaciones.

Se aplican en la capa de datos antes de escribir (sirven para cualquier
pantalla o proceso que llame) y también al pedir cada dato, para avisar antes.
Los largos máximos son los de las columnas de PostgreSQL.
"""

import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from app.utils.validaciones_terceros import validar_cuit

# ------------------------------------------------------------------ límites

IMPORTE_MAXIMO = Decimal("100000000.00")      # por operación
PESO_MAXIMO_KG = Decimal("100000")
DISTANCIA_MAXIMA_KM = Decimal("40000")
CAPACIDAD_MAXIMA_T = Decimal("100")
LARGO_DESCRIPCION = 1000
LARGO_MENSAJE = 2000
LARGO_NOMBRE_GRUPO = 100

LARGOS_CONTACTO = {
    "razon_social": 150,
    "email": 150,
    "telefono": 30,
    "direccion": 255,
    "pais": 80,
}
LARGOS_USUARIO = {"nombre": 80, "apellido": 80, "email": 150}

_EMAIL = re.compile(r"^[A-Za-z0-9._%+'-]+@[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?"
                    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)*\.[A-Za-z]{2,}$")
_TELEFONO = re.compile(r"^\+?[0-9 ()\-]+$")
_ID_FISCAL_EXTRANJERO = re.compile(r"^[0-9A-Z.\-]{6,13}$")


def _normalizar(texto):
    texto = unicodedata.normalize("NFKD", str(texto or "").strip())
    return "".join(c for c in texto if not unicodedata.combining(c)).casefold()


def _articulo(nombre):
    primera = str(nombre).split(" ", 1)[0].lower()
    return {"la": "obligatoria", "las": "obligatorias", "los": "obligatorios"}.get(primera, "obligatorio")


# ------------------------------------------------------------------ textos

def validar_largo(valor, nombre, maximo, obligatorio=True):
    """Texto sin espacios de más; None si es opcional y está vacío."""
    texto = str(valor or "").strip()
    if not texto:
        if obligatorio:
            raise ValueError(f"{nombre} es {_articulo(nombre)}.")
        return None
    if len(texto) > maximo:
        raise ValueError(f"{nombre} no puede superar {maximo} caracteres.")
    return texto


def validar_email(valor, obligatorio=True, maximo=150):
    texto = validar_largo(valor, "El email", maximo, obligatorio)
    if texto is None:
        return None
    if not _EMAIL.match(texto) or ".." in texto:
        raise ValueError("El email ingresado no es válido.")
    return texto


def validar_telefono(valor, obligatorio=False):
    texto = validar_largo(valor, "El teléfono", LARGOS_CONTACTO["telefono"], obligatorio)
    if texto is None:
        return None
    digitos = sum(c.isdigit() for c in texto)
    if not _TELEFONO.match(texto) or digitos < 6:
        raise ValueError("El teléfono ingresado no es válido (al menos 6 dígitos; "
                         "se admiten +, espacios, guiones y paréntesis).")
    return texto


def es_argentina(pais):
    return _normalizar(pais) in {"argentina", "republica argentina", "ar"}


def validar_identificacion_fiscal(valor, pais):
    """CUIT con dígito verificador si el país es Argentina; si no, solo formato."""
    if es_argentina(pais):
        return validar_cuit(valor)
    texto = str(valor or "").strip().upper().replace(" ", "")
    if not texto:
        raise ValueError("La identificación fiscal es obligatoria.")
    if not _ID_FISCAL_EXTRANJERO.match(texto) or sum(c.isdigit() for c in texto) < 5:
        raise ValueError("La identificación fiscal debe tener de 6 a 13 caracteres "
                         "(números, puntos, guiones o K) con al menos 5 dígitos.")
    return texto


# ------------------------------------------------------------------ importes

def validar_importe(valor, nombre="El importe", permitir_cero=False, maximo=IMPORTE_MAXIMO):
    """Decimal con hasta 2 decimales, positivo (o cero) y no mayor al máximo."""
    try:
        importe = Decimal(str(valor).strip().replace(",", ".")) if isinstance(valor, str) \
            else Decimal(str(valor))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"{nombre} no es un importe válido.") from None
    if not importe.is_finite():
        raise ValueError(f"{nombre} no es un importe válido.")
    if importe != importe.quantize(Decimal("0.01")):
        raise ValueError(f"{nombre} admite como máximo 2 decimales.")
    if importe < 0 or (importe == 0 and not permitir_cero):
        raise ValueError(f"{nombre} debe ser mayor a cero." if not permitir_cero
                         else f"{nombre} no puede ser negativo.")
    controlar_maximo(importe, nombre, maximo)
    return importe.quantize(Decimal("0.01"))


def controlar_maximo(importe, nombre="El importe", maximo=IMPORTE_MAXIMO):
    if importe > maximo:
        from app.utils import formato
        raise ValueError(f"{nombre} no puede superar {formato.dinero(maximo)} por operación.")
    return importe


def controlar_cantidad(valor, nombre, maximo, unidad):
    if valor > maximo:
        from app.utils import formato
        raise ValueError(f"{nombre} no puede superar {formato.compacto(maximo)} {unidad}.")
    return valor


# ------------------------------------------------------------------ fechas

def validar_rango(desde, hasta, nombre_desde="La fecha desde", nombre_hasta="la fecha hasta"):
    if desde is not None and hasta is not None and hasta < desde:
        raise ValueError(f"{nombre_desde} no puede ser posterior a {nombre_hasta}.")
    return desde, hasta


def validar_no_futura(fecha, nombre, hoy=None):
    if fecha is None:
        return None
    hoy = hoy or date.today()
    dia = fecha.date() if isinstance(fecha, datetime) else fecha
    if dia > hoy:
        raise ValueError(f"{nombre} no puede ser futura.")
    return fecha


# ------------------------------------------------------------------ registros completos

def validar_contacto(datos, identificacion="cuit", email_obligatorio=True,
                     direccion_obligatoria=False, cuit_por_pais=False):
    """Normaliza y valida razón social, CUIT, email, teléfono, dirección y país.

    cuit_por_pais=True: clientes (CUIT con dígito si es de Argentina; si no, formato).
    False: proveedores y operadores (siempre CUIT argentino).
    """
    limpio = dict(datos)
    limpio["razon_social"] = validar_largo(datos.get("razon_social"), "La razón social",
                                           LARGOS_CONTACTO["razon_social"])
    limpio["pais"] = validar_largo(datos.get("pais"), "El país", LARGOS_CONTACTO["pais"])
    if cuit_por_pais:
        limpio[identificacion] = validar_identificacion_fiscal(datos.get(identificacion), limpio["pais"])
    else:
        limpio[identificacion] = validar_cuit(datos.get(identificacion))
    limpio["email"] = validar_email(datos.get("email"), obligatorio=email_obligatorio)
    limpio["telefono"] = validar_telefono(datos.get("telefono"))
    limpio["direccion"] = validar_largo(datos.get("direccion"), "La dirección",
                                        LARGOS_CONTACTO["direccion"], direccion_obligatoria)
    return limpio


def validar_datos_usuario(nombre, apellido, email):
    return (
        validar_largo(nombre, "El nombre", LARGOS_USUARIO["nombre"]),
        validar_largo(apellido, "El apellido", LARGOS_USUARIO["apellido"]),
        validar_email(email, maximo=LARGOS_USUARIO["email"]),
    )
