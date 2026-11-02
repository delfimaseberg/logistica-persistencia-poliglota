import unicodedata
from datetime import datetime, timezone


TIPOS_VEHICULO = ["Terrestre", "Marítimo", "Aéreo"]
ESTADOS_VEHICULO = ["Disponible", "En uso", "Mantenimiento", "Inactivo"]
MEDIOS_TRANSPORTE = ["Terrestre", "Marítimo", "Aéreo"]


def normalizar(texto):
    texto = unicodedata.normalize("NFKD", texto.strip())
    texto = "".join(
        caracter for caracter in texto
        if not unicodedata.combining(caracter)
    )
    return texto.casefold()


def validar_opcion_flexible(valor, opciones, nombre):
    valor = valor.strip()

    for opcion in opciones:
        if normalizar(valor) == normalizar(opcion):
            return opcion

    raise ValueError(
        f"{nombre} debe ser uno de estos valores: "
        + ", ".join(opciones)
    )


def es_obligatorio(nombre):
    """'La ubicación' -> 'La ubicación es obligatoria.'"""
    primera = str(nombre).split(" ", 1)[0].lower()
    terminacion = {"la": "obligatoria", "las": "obligatorias", "los": "obligatorios"}.get(primera, "obligatorio")
    return f"{nombre} es {terminacion}."


def validar_texto(valor, nombre, maximo=150):
    valor = valor.strip()

    if not valor:
        raise ValueError(es_obligatorio(nombre))

    if len(valor) > maximo:
        raise ValueError(
            f"{nombre} no puede superar {maximo} caracteres."
        )

    return valor


def validar_identificacion(valor):
    return validar_texto(valor, "La identificación", 50).upper()


def validar_fecha(valor, nombre):
    valor = valor.strip()

    try:
        fecha = datetime.strptime(valor, "%Y-%m-%d")
    except ValueError:
        raise ValueError(
            f"{nombre} debe ser una fecha real "
            "con formato AAAA-MM-DD."
        )

    # Se usa UTC para almacenar un instante inequívoco.
    # La aplicación solicita únicamente el día.
    return fecha.replace(tzinfo=timezone.utc)


def validar_rango_fechas(fecha_salida, fecha_llegada):
    if fecha_llegada < fecha_salida:
        raise ValueError(
            "La fecha estimada de llegada no puede ser "
            "anterior a la fecha de salida."
        )


def validar_entero_positivo_logistica(valor, nombre):
    try:
        numero = int(valor.strip())
    except ValueError:
        raise ValueError(f"{nombre} debe ser un número entero.")

    if numero <= 0:
        raise ValueError(f"{nombre} debe ser mayor que cero.")

    return numero