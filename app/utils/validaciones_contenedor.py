import re
from decimal import Decimal, InvalidOperation

from app.utils.validaciones_logistica import (
    validar_opcion_flexible
)


TIPOS_CONTENEDOR = [
    "Seco",
    "Refrigerado",
    "Tanque",
    "Open Top"
]

ESTADOS_CONTENEDOR = [
    "Disponible",
    "En uso",
    "Mantenimiento",
    "Inactivo"
]


def validar_tipo_contenedor(valor):
    return validar_opcion_flexible(
        valor,
        TIPOS_CONTENEDOR,
        "El tipo de contenedor"
    )


def validar_estado_contenedor(valor):
    return validar_opcion_flexible(
        valor,
        ESTADOS_CONTENEDOR,
        "El estado del contenedor"
    )


def validar_capacidad(valor):
    try:
        capacidad = Decimal(valor.strip().replace(",", "."))
    except InvalidOperation:
        raise ValueError("La capacidad debe ser un número válido.")

    if not capacidad.is_finite():
        raise ValueError("La capacidad debe ser un número finito.")

    if capacidad <= 0:
        raise ValueError("La capacidad debe ser mayor que cero.")

    if capacidad > Decimal("100"):
        raise ValueError("La capacidad no puede superar 100 toneladas.")

    if capacidad.as_tuple().exponent < -2:
        raise ValueError(
            "La capacidad admite como máximo dos decimales."
        )

    return capacidad


def validar_codigo_internacional(valor):
    codigo = valor.strip().upper().replace(" ", "")

    if not re.fullmatch(r"[A-Z]{3}U[0-9]{7}", codigo):
        raise ValueError(
            "El código debe tener 3 letras, la letra U "
            "y 7 dígitos. Ejemplo: MSCU1234566."
        )

    valores = {}
    numero = 10

    for letra in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        while numero % 11 == 0:
            numero += 1

        valores[letra] = numero
        numero += 1

    suma = 0

    for posicion, caracter in enumerate(codigo[:10]):
        valor = (
            int(caracter)
            if caracter.isdigit()
            else valores[caracter]
        )

        suma += valor * (2 ** posicion)

    resto = (suma % 11) % 10

    if resto != int(codigo[10]):
        raise ValueError(
            "El dígito de control del código internacional "
            "no es válido."
        )

    return codigo