import re
from datetime import datetime


def es_obligatorio(nombre):
    """'La dirección' -> 'La dirección es obligatoria.' (concuerda con el artículo)."""
    primera = str(nombre).split(" ", 1)[0].lower()
    terminacion = {"la": "obligatoria", "las": "obligatorias", "los": "obligatorios"}.get(primera, "obligatorio")
    return f"{nombre} es {terminacion}."


def texto_obligatorio(valor, nombre_campo):
    valor = valor.strip()

    if not valor:
        raise ValueError(es_obligatorio(nombre_campo))

    return valor


def validar_entero_positivo(valor, nombre_campo):
    try:
        numero = int(valor)
    except ValueError:
        raise ValueError(f"{nombre_campo} debe ser un número entero.")

    if numero <= 0:
        raise ValueError(f"{nombre_campo} debe ser mayor que 0.")

    return numero


def validar_email(email):
    email = email.strip()

    patron = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"

    if not re.match(patron, email):
        raise ValueError("El email ingresado no es válido.")

    return email


def validar_telefono(telefono):
    telefono = telefono.strip()

    patron = r"^\+?[0-9\s\-()]+$"

    if not telefono:
        return telefono

    if not re.match(patron, telefono):
        raise ValueError("El teléfono ingresado no es válido.")

    return telefono


def validar_opcion(valor, opciones, nombre_campo):
    valor = valor.strip()

    opciones_normalizadas = {
        opcion.lower(): opcion
        for opcion in opciones
    }

    if valor.lower() not in opciones_normalizadas:
        raise ValueError(
            f"{nombre_campo} debe ser uno de los siguientes valores: "
            f"{', '.join(opciones)}."
        )

    return opciones_normalizadas[valor.lower()]


def validar_fecha(fecha):
    try:
        return datetime.strptime(fecha, "%Y-%m-%d")
    except ValueError:
        raise ValueError(
            "La fecha debe tener el formato AAAA-MM-DD."
        )