"""Alertas climáticas cargadas a mano (MongoDB, colección alertas_climaticas).

Fuente de riesgo climático sin API externa: un usuario interno registra el
fenómeno, la ubicación (ciudad o país) y el período en que rige.
"""

import unicodedata
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from bson import ObjectId
from bson.errors import InvalidId

from app.database.mongo_connection import get_mongo_database


ZONA = ZoneInfo("America/Argentina/Buenos_Aires")  # las fechas de las alertas se toman en hora argentina
SEVERIDADES_CLIMA = ("Baja", "Media", "Alta", "Extrema")  # severidades posibles, de menor a mayor


def normalizar_lugar(texto):  # nombre de lugar comparable; la usan las alertas y las predicciones
    """'Córdoba ' -> 'cordoba' (sin acentos ni mayúsculas)."""
    sin_acentos = unicodedata.normalize("NFKD", str(texto or ""))
    sin_acentos = "".join(c for c in sin_acentos if not unicodedata.combining(c))
    return " ".join(sin_acentos.casefold().split())


def coleccion():  # colección alertas_climaticas de MongoDB con sus índices
    col = get_mongo_database()["alertas_climaticas"]
    col.create_index([("ubicacion_normalizada", 1), ("inicio", 1), ("fin", 1)],
                     name="idx_clima_ubicacion_periodo")
    col.create_index([("estado", 1), ("fin", 1)], name="idx_clima_estado_fin")
    return col


def validar(ubicacion, fenomeno, severidad, desde, hasta):  # controla los datos; la usa registrar_alerta_climatica
    ubicacion = " ".join(str(ubicacion or "").split())
    fenomeno = " ".join(str(fenomeno or "").split())
    if not ubicacion or len(ubicacion) > 80:
        raise ValueError("La ubicación es obligatoria (hasta 80 caracteres).")
    if not fenomeno or len(fenomeno) > 80:
        raise ValueError("El fenómeno es obligatorio (hasta 80 caracteres).")
    if severidad not in SEVERIDADES_CLIMA:
        raise ValueError("Severidad inválida (Baja, Media, Alta o Extrema).")
    if desde > hasta:
        raise ValueError("La fecha 'desde' no puede ser posterior a 'hasta'.")
    if (hasta - desde).days > 60:  # una alerta dura como mucho 60 días
        raise ValueError("Una alerta climática no puede durar más de 60 días.")
    return ubicacion, fenomeno


def registrar_alerta_climatica(ubicacion, fenomeno, severidad, desde, hasta,  # guarda una alerta Vigente; la usan la opción 1 de alertas climáticas y la carga de ejemplo
                               id_usuario, descripcion=None, ahora=None):
    """desde/hasta: fechas (date) inclusive, en hora argentina."""
    ubicacion, fenomeno = validar(ubicacion, fenomeno, severidad, desde, hasta)
    documento = {
        "ubicacion": ubicacion,
        "ubicacion_normalizada": normalizar_lugar(ubicacion),  # con este campo se busca por lugar
        "fenomeno": fenomeno,
        "severidad": severidad,
        "descripcion": (descripcion or "").strip() or None,
        "fecha_desde": desde.isoformat(),
        "fecha_hasta": hasta.isoformat(),
        # [inicio, fin) en instantes, para comparar con los tramos.
        "inicio": datetime.combine(desde, time(), ZONA),
        "fin": datetime.combine(hasta + timedelta(days=1), time(), ZONA),  # el día hasta queda incluido
        "estado": "Vigente",
        "fuente": "Carga manual",
        "registrada_por": id_usuario,
        "fecha_registro": ahora or datetime.now(ZONA),
    }
    return str(coleccion().insert_one(documento).inserted_id)


def listar_alertas_climaticas(incluir_vencidas=False, incluir_anuladas=False, ahora=None):  # alertas vigentes y no vencidas; la usan el menú de clima y los reportes
    filtro = {}
    if not incluir_anuladas:
        filtro["estado"] = "Vigente"
    if not incluir_vencidas:
        filtro["fin"] = {"$gt": ahora or datetime.now(ZONA)}  # todavía no terminaron
    return list(coleccion().find(filtro).sort([("inicio", 1), ("ubicacion", 1)]))


def alertas_para_lugares(lugares_normalizados):  # alertas de esos lugares, de cualquier fecha; la usa armar_datos_riesgo
    """Alertas vigentes (no anuladas) de esas ubicaciones, de cualquier período."""
    if not lugares_normalizados:
        return []
    return list(coleccion().find({
        "estado": "Vigente",
        "ubicacion_normalizada": {"$in": sorted(set(lugares_normalizados))},
    }))


def anular_alerta_climatica(id_alerta, id_usuario, ahora=None):  # pasa la alerta a Anulada y queda en el historial; la usa la opción 3 de alertas climáticas
    try:
        identificador = ObjectId(str(id_alerta))
    except (InvalidId, TypeError):
        return False
    resultado = coleccion().update_one(
        {"_id": identificador, "estado": "Vigente"},  # solo se anula si seguía vigente
        {"$set": {"estado": "Anulada", "anulada_por": id_usuario,
                  "fecha_anulacion": ahora or datetime.now(ZONA)}})
    return resultado.matched_count == 1
