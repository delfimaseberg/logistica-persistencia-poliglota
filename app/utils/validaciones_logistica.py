import unicodedata
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo


ZONA_ARGENTINA = ZoneInfo("America/Argentina/Buenos_Aires")


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


def validar_fecha(valor, nombre, fin_del_dia=False):
    """Día AAAA-MM-DD interpretado en hora argentina.

    Devuelve el inicio del día (00:00:00) o, con fin_del_dia, su último
    segundo (23:59:59): una llegada estimada vale hasta el final de ese día.
    """
    valor = valor.strip()

    try:
        dia = datetime.strptime(valor, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError(
            f"{nombre} debe ser una fecha real "
            "con formato AAAA-MM-DD."
        )

    hora = time(23, 59, 59) if fin_del_dia else time(0, 0, 0)
    return datetime.combine(dia, hora, ZONA_ARGENTINA)


def dia_local(fecha):
    """Fecha calendario en hora argentina de un instante."""
    if fecha.tzinfo is None:
        fecha = fecha.replace(tzinfo=timezone.utc)
    return fecha.astimezone(ZONA_ARGENTINA).date()


def sale_despues_de_llegar(fecha_salida, llegada_anterior):
    """El tramo nuevo puede salir el mismo día en que llega el anterior."""
    return dia_local(fecha_salida) >= dia_local(llegada_anterior)


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