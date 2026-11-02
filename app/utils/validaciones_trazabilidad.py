
from datetime import datetime, timedelta, timezone
from math import isfinite
from zoneinfo import ZoneInfo

from app.utils import formato
from app.utils.validaciones_logistica import normalizar


ZONA_ARGENTINA = ZoneInfo("America/Argentina/Buenos_Aires")

TIPOS_EVENTO = [
    "CARGA_INICIADA",
    "EN_TRANSITO",
    "ADUANA",
    "RETRASO",
    "DESCARGA",
    "ENTREGADO"
]

# Datos específicos de cada tipo de evento (parte "flexible" del documento).
DETALLE_POR_TIPO = {
    "ADUANA": [("documento", "texto")],
    "RETRASO": [("motivo", "texto"), ("demora_horas", "numero")]
}


def normalizar_nombre_grafo(texto):
    """Normaliza nombres de Ubicacion/Operador antes de usarlos en Neo4j.

    'Montevideo', 'MONTEVIDEO' y ' montevideo ' dan el mismo valor.
    """
    if texto is None:
        return ""

    return " ".join(normalizar(str(texto)).split())


def validar_texto_opcional(valor, nombre, maximo=200):
    valor = valor.strip()

    if len(valor) > maximo:
        raise ValueError(
            f"{nombre} no puede superar {maximo} caracteres."
        )

    return valor or None


def validar_numero_opcional(valor, nombre):
    valor = valor.strip().replace(",", ".")

    if not valor:
        return None

    try:
        numero = float(valor)
    except ValueError:
        raise ValueError(f"{nombre} debe ser un número.")

    if not isfinite(numero) or numero < 0:
        raise ValueError(f"{nombre} debe ser un número válido (>= 0).")

    return numero


def validar_coordenada(valor, nombre, minimo, maximo):
    valor = valor.strip().replace(",", ".")

    if not valor:
        return None

    try:
        numero = float(valor)
    except ValueError:
        raise ValueError(f"{nombre} debe ser un número.")

    if not isfinite(numero) or not minimo <= numero <= maximo:
        raise ValueError(
            f"{nombre} debe estar entre {minimo} y {maximo}."
        )

    return numero


def parsear_fecha_hora(texto, ahora=None):
    """Convierte 'AAAA-MM-DD HH:MM' (hora argentina) a UTC.

    Si el texto está vacío devuelve el momento actual. No admite fechas
    futuras, pero sí pasadas: permite cargar eventos incorporados tarde.
    """
    ahora = ahora or datetime.now(timezone.utc)
    texto = texto.strip()

    if not texto:
        return ahora

    try:
        local = datetime.strptime(texto, "%Y-%m-%d %H:%M")
    except ValueError:
        raise ValueError(
            "La fecha debe tener formato AAAA-MM-DD HH:MM."
        )

    fecha = local.replace(tzinfo=ZONA_ARGENTINA).astimezone(
        timezone.utc
    )

    if fecha > ahora + timedelta(minutes=1):
        raise ValueError("La fecha del evento no puede ser futura.")

    return fecha


def validar_evento_permitido(estado_envio, tipo, tipos_registrados):
    """Valida estados incompatibles.

    Lanza ValueError si el evento no se puede registrar. Devuelve una
    lista de advertencias (no bloqueantes) para mostrar al usuario: el
    historial debe poder reflejar lo ocurrido aunque falten eventos.
    """
    estado = normalizar(estado_envio or "")

    if estado == "cancelado":
        raise ValueError(
            "El envío está cancelado: no admite más eventos."
        )

    if estado == "entregado":
        raise ValueError(
            "El envío ya figura como entregado: no admite más eventos."
        )

    if tipo == "ENTREGADO" and "ENTREGADO" in tipos_registrados:
        raise ValueError("El envío ya tiene un evento ENTREGADO.")

    advertencias = []

    if tipo == "ENTREGADO" and "EN_TRANSITO" not in tipos_registrados:
        advertencias.append(
            "El envío no tiene un evento EN_TRANSITO registrado."
        )

    if tipo == "DESCARGA" and "EN_TRANSITO" not in tipos_registrados:
        advertencias.append(
            "El envío no tiene un evento EN_TRANSITO registrado."
        )

    return advertencias


def estado_nuevo_por_evento(tipo, estado_actual):
    """Estado del envío que implica el evento, o None si no cambia."""
    estado = normalizar(estado_actual or "")

    # Iniciar la carga no implica que el vehículo haya salido.
    # El envío pasa a En tránsito cuando se registra EN_TRANSITO.
    if tipo == "EN_TRANSITO" and estado == "pendiente":
        return "En tránsito"

    if tipo == "ENTREGADO":
        return "Entregado"

    return None


def ultimos_meses(cantidad, ahora=None):
    """Lista de 'AAAA-MM' en orden cronológico, terminando en el mes actual."""
    ahora = ahora or datetime.now(timezone.utc)
    anio, mes = ahora.year, ahora.month
    meses = []

    for _ in range(cantidad):
        meses.append(f"{anio:04d}-{mes:02d}")
        mes -= 1

        if mes == 0:
            mes = 12
            anio -= 1

    return list(reversed(meses))


def muestrear(elementos, maximo):
    """Reduce una lista conservando el primero y el último elemento."""
    if len(elementos) <= maximo or maximo < 2:
        return list(elementos)

    paso = (len(elementos) - 1) / (maximo - 1)
    indices = sorted({round(i * paso) for i in range(maximo)})

    return [elementos[i] for i in indices]


def _con_zona(fecha):
    if fecha.tzinfo is None:
        return fecha.replace(tzinfo=timezone.utc)

    return fecha


def fusionar_recorrido(eventos, puntos_gps):
    """Une eventos (MongoDB) y posiciones GPS (Cassandra) en una línea
    de tiempo ordenada.
    """
    linea = []

    for evento in eventos:
        ubicacion = (evento.get("ubicacion") or {}).get("nombre", "-")
        linea.append({
            "fecha": _con_zona(evento["fecha_hora"]),
            "origen": "EVENTO",
            "texto": (
                f"{formato.evento(evento['tipo'])} en {ubicacion} "
                f"(envío {evento['envio_id']})"
            )
        })

    for punto in puntos_gps:
        linea.append({
            "fecha": _con_zona(punto["fecha_hora"]),
            "origen": "GPS",
            "texto": (
                f"latitud {formato.numero(punto['lat'], 5)} | "
                f"longitud {formato.numero(punto['lon'], 5)} "
                f"(sensor {punto['sensor_id']})"
            )
        })

    linea.sort(key=lambda item: item["fecha"])

    return linea
