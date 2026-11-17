"""Reglas de detección sobre lecturas IoT (funciones puras, sin bases).

- Umbrales de la carga (temperatura, humedad, vibración, batería): los
  configura el ABM de reglas de alerta.
- Fallas del sensor (aclaración del profesor: un sensor que mide mal):
  valores físicamente imposibles, lecturas congeladas y saltos bruscos.
"""

from datetime import timedelta, timezone
from math import isfinite

from app.repositories.regla_alerta_repository import ORDEN_SEVERIDAD, VARIABLES
from app.utils import formato


# Lo que un sensor puede medir de verdad; fuera de esto, el sensor falla.
RANGOS_FISICOS = {
    "temperatura": (-50.0, 90.0),
    "humedad": (0.0, 100.0),
    "vibracion": (0.0, 1000.0),
    "bateria": (0.0, 100.0),
    "gps_latitud": (-90.0, 90.0),
    "gps_longitud": (-180.0, 180.0),
}
NOMBRES = {  # nombre de cada campo para los textos
    "temperatura": "Temperatura", "humedad": "Humedad", "vibracion": "Vibración",
    "bateria": "Batería", "gps_latitud": "Latitud", "gps_longitud": "Longitud",
}
VARIABLES_CARGA = ("temperatura", "humedad", "vibracion", "bateria")  # las variables que se comparan con umbrales
VENTANA_SALTO = timedelta(minutes=60)  # un salto cuenta solo entre lecturas separadas por menos de una hora

FALLA_VALOR = "Falla de sensor: valor imposible"  # tipos de alerta de falla del sensor
FALLA_CONGELADA = "Falla de sensor: lecturas congeladas"
FALLA_SALTO = "Falla de sensor: salto brusco"

# Mismos valores que la carga inicial de la migración 015 (para tests y
# como referencia; la detección usa las reglas activas de la base).
REGLAS_POR_DEFECTO = {  # reglas iniciales: variable y límite, con valor, severidad y nombre
    ("temperatura", "MIN"): [(2.0, "Alta", "Temperatura baja")],
    ("temperatura", "MAX"): [(8.0, "Alta", "Temperatura alta")],
    ("humedad", "MAX"): [(80.0, "Media", "Humedad alta")],
    ("vibracion", "MAX"): [(15.0, "Alta", "Vibración alta")],
    ("bateria", "MIN"): [(20.0, "Media", "Batería baja")],
    ("horas_sin_transmision", "MAX"): [(24.0, "Media", "Sensor sin transmisión reciente")],
    ("salto_temperatura", "MAX"): [(10.0, "Media", "Salto brusco de temperatura")],
    ("lecturas_congeladas", "MAX"): [(6.0, "Media", "Lecturas congeladas")],
}


def nombre_tipo_sensor(tipo):  # tipo de sensor para los textos; la usa descripcion_sin_transmision
    """Tipo de sensor para un texto: 'humedad', 'temperatura'; las siglas
    (GPS) quedan en mayúsculas."""
    tipo = " ".join(str(tipo or "").split())
    return tipo if tipo.isupper() else tipo.lower()


def descripcion_sin_transmision(tipo_sensor, codigo_contenedor, ultima=None, horas=None):  # texto de la alerta de sensor sin transmisión; la usa la revisión de sensores
    """Texto de las alertas de sensor sin lecturas o sin transmisión reciente.

    ultima: fecha (datetime) de la última lectura; sin ella, "sin lecturas".
    """
    sensor = f"El sensor de {nombre_tipo_sensor(tipo_sensor)} del contenedor {codigo_contenedor}"
    if ultima is None:
        return f"{sensor} no tiene lecturas registradas."
    if ultima.tzinfo is None:
        ultima = ultima.replace(tzinfo=timezone.utc)
    from zoneinfo import ZoneInfo
    local = ultima.astimezone(ZoneInfo("America/Argentina/Buenos_Aires"))
    return f"{sensor} no transmite desde {local:%d/%m/%Y %H:%M}. Umbral: {formato.compacto(horas)} horas."


def _numero(valor):  # pasa a float o None; lo usan las funciones de detección
    """float, None si falta o no es número. NaN e infinito se devuelven tal cual."""
    if valor is None or isinstance(valor, bool):
        return None
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def _fecha(lectura):  # fecha de la lectura con zona horaria
    fecha = getattr(lectura, "fecha_hora", None)
    if fecha is not None and fecha.tzinfo is None:
        fecha = fecha.replace(tzinfo=timezone.utc)
    return fecha


def valores_imposibles(lectura):  # campos fuera del rango físico; la usan las fallas y la validación de umbrales
    """[(campo, valor)] con valores no finitos o fuera del rango físico."""
    resultado = []
    for campo, (minimo, maximo) in RANGOS_FISICOS.items():
        valor = _numero(getattr(lectura, campo, None))
        if valor is None:
            continue
        if not isfinite(valor) or not minimo <= valor <= maximo:  # valor imposible: no numérico o fuera de rango
            resultado.append((campo, valor))
    return resultado


def evaluar_umbrales(lectura, vigentes):  # compara la lectura con los umbrales activos; la usa detectar_anomalias
    """[(tipo, severidad, descripción)] según las reglas activas.

    Por variable y límite se informa solo la regla más severa que se cumple.
    Los valores no numéricos o no finitos se ignoran (los informa la falla).
    """
    resultados = []
    for variable in VARIABLES_CARGA:
        valor = _numero(getattr(lectura, variable, None))
        if valor is None or not isfinite(valor):
            continue
        for limite in ("MIN", "MAX"):
            cumplidas = [
                (umbral, severidad) for umbral, severidad, _ in vigentes.get((variable, limite), [])
                if (valor < umbral if limite == "MIN" else valor > umbral)  # MIN: alerta si baja del umbral; MAX: si lo supera
            ]
            if not cumplidas:
                continue
            umbral, severidad = max(cumplidas, key=lambda r: ORDEN_SEVERIDAD.get(r[1], -1))  # si se cumplen varias, se informa la más severa
            tipo = f"{VARIABLES[variable][0]} {'baja' if limite == 'MIN' else 'alta'}"
            resultados.append((tipo, severidad, f"{tipo}: valor {formato.compacto(valor)}, "
                                                f"límite {formato.compacto(umbral)}"))
    return resultados


def _regla(vigentes, variable):  # la regla MAX que dispara primero; la usa fallas_de_sensor
    """(valor, severidad) de la regla MAX activa menos exigente, o None."""
    reglas = vigentes.get((variable, "MAX"))
    if not reglas:
        return None
    valor, severidad, _ = min(reglas, key=lambda r: r[0])
    return valor, severidad


def lecturas_congeladas(lecturas, cantidad):  # si las últimas N lecturas son idénticas; la usa fallas_de_sensor
    """True si las últimas `cantidad` lecturas tienen igual temperatura y humedad.

    `lecturas` va de la más nueva a la más vieja.
    """
    cantidad = int(cantidad)
    serie = list(lecturas)[:cantidad]
    if cantidad < 2 or len(serie) < cantidad:
        return False
    valores = {(_numero(l.temperatura), _numero(l.humedad)) for l in serie}
    if len(valores) != 1:  # un solo par distinto: el sensor quedó trabado
        return False
    temperatura, humedad = next(iter(valores))
    return temperatura is not None or humedad is not None


def saltos_bruscos(lecturas, maximo, ventana=VENTANA_SALTO):  # cambios de temperatura demasiado grandes entre lecturas seguidas; la usa fallas_de_sensor
    """[(anterior, posterior, diferencia)] entre lecturas seguidas y cercanas.

    Ignora pares con valores imposibles (esos ya son otra falla).
    """
    ordenadas = sorted((l for l in lecturas if _fecha(l) is not None), key=_fecha)
    saltos = []
    for anterior, posterior in zip(ordenadas, ordenadas[1:]):
        t1, t2 = _numero(anterior.temperatura), _numero(posterior.temperatura)
        if t1 is None or t2 is None or not (isfinite(t1) and isfinite(t2)):
            continue
        if valores_imposibles(anterior) or valores_imposibles(posterior):
            continue
        if _fecha(posterior) - _fecha(anterior) > ventana:  # muy separadas en el tiempo: no es un salto
            continue
        diferencia = abs(t2 - t1)
        if diferencia > maximo:  # salto brusco: más grados que el máximo de la regla
            saltos.append((anterior, posterior, round(diferencia, 2)))
    return saltos


def fallas_de_sensor(lecturas, vigentes):  # valor imposible, lecturas congeladas y saltos bruscos; la usa revisar_lecturas_sensores
    """Fallas en las lecturas recientes (de la más nueva a la más vieja).

    Devuelve [(tipo, severidad, descripción, id_lectura_de_referencia)].
    """
    lecturas = list(lecturas)
    if not lecturas:
        return []
    fallas = []
    ultima = lecturas[0]
    imposibles = valores_imposibles(ultima)  # el valor imposible se mira en la última lectura
    if imposibles:
        detalle = "; ".join(f"{NOMBRES[c]} = {formato.compacto(v, 5) if isfinite(v) else 'no numérico'}"
                            for c, v in imposibles)
        fallas.append((FALLA_VALOR, "Alta",
                       f"El sensor informó valores imposibles: {detalle}.", ultima.id_lectura))

    regla = _regla(vigentes, "lecturas_congeladas")
    if regla and lecturas_congeladas(lecturas, regla[0]):  # la alerta queda en la primera lectura congelada
        cantidad = int(regla[0])
        primera = lecturas[cantidad - 1]
        # Solo las variables que mide el sensor (las demás vienen vacías).
        medidas = [f"{nombre} {formato.compacto(valor)}" for nombre, valor in
                   (("temperatura", _numero(ultima.temperatura)), ("humedad", _numero(ultima.humedad)))
                   if valor is not None]
        fallas.append((FALLA_CONGELADA, regla[1],
                       f"Las últimas {cantidad} lecturas son idénticas "
                       f"({', '.join(medidas)}).",
                       primera.id_lectura))

    regla = _regla(vigentes, "salto_temperatura")
    if regla:
        for anterior, posterior, diferencia in saltos_bruscos(lecturas, regla[0]):  # una alerta por cada salto
            minutos = int((_fecha(posterior) - _fecha(anterior)).total_seconds() // 60)
            fallas.append((FALLA_SALTO, regla[1],
                           f"La temperatura pasó de {formato.compacto(anterior.temperatura)} a "
                           f"{formato.compacto(posterior.temperatura)} °C en {minutos} min "
                           f"(salto de {formato.compacto(diferencia)} °C; máximo {formato.compacto(regla[0])} °C).",
                           posterior.id_lectura))
    return fallas


def es_lectura_valida_para_umbrales(lectura):  # si la lectura sirve para evaluar la carga; la usa detectar_anomalias
    """Una lectura con valores imposibles no se usa para evaluar la carga."""
    return not valores_imposibles(lectura)
