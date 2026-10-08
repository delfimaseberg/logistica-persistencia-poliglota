
from datetime import date, datetime

from app.utils.validaciones_logistica import (
    validar_opcion_flexible,
    validar_texto,
    validar_entero_positivo_logistica
)


TIPOS_SENSOR = [
    "Temperatura",
    "Humedad",
    "GPS",
    "Vibración",
    "Apertura"
]

ESTADOS_SENSOR = [
    "Activo",
    "Inactivo",
    "Mantenimiento"
]


def validar_tipo_sensor(valor):
    return validar_opcion_flexible(
        valor,
        TIPOS_SENSOR,
        "El tipo de sensor"
    )


def validar_estado_sensor(valor):
    return validar_opcion_flexible(
        valor,
        ESTADOS_SENSOR,
        "El estado del sensor"
    )


def validar_fabricante(valor):
    valor = valor.strip()

    if not valor:
        return None

    return validar_texto(
        valor,
        "El fabricante",
        100
    )


def validar_fecha_instalacion(valor):
    valor = valor.strip()

    if not valor:
        return None

    try:
        fecha = datetime.strptime(
            valor, "%Y-%m-%d"
        ).date()
    except ValueError:
        raise ValueError(
            "La fecha debe tener formato AAAA-MM-DD "
            "y ser una fecha válida."
        )

    if fecha > date.today():
        raise ValueError(
            "La fecha de instalación no puede ser futura."
        )

    return fecha


def validar_id_sensor(valor):
    return validar_entero_positivo_logistica(
        valor, "El ID del sensor"
    )


def validar_id_contenedor(valor):
    return validar_entero_positivo_logistica(
        valor, "El ID del contenedor"
    )
