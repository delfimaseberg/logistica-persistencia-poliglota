"""Generación de alertas con emisión de mensajes (requisito 26).

emitir_alerta guarda la alerta (MongoDB, colección alertas) y, si es nueva,
deja un mensaje de tipo "Alerta" a todos los usuarios internos activos y a
los usuarios del cliente del envío (si la alerta tiene envío). Un índice
único (alerta, destinatario) evita mensajes repetidos.
"""

from datetime import timezone
from zoneinfo import ZoneInfo

from app.database.postgres_connection import get_postgres_connection
from app.repositories.alerta_repository import marcar_mensajes_emitidos, registrar_alerta
from app.repositories.mensajeria_repository import (
    destinatarios_alerta,
    registrar_mensaje_alerta,
)
from app.utils.logger import obtener_logger


logger = obtener_logger("alertas")  # deja registro en logs/app.log
ZONA = ZoneInfo("America/Argentina/Buenos_Aires")


def codigo_contenedor(id_contenedor):  # código del contenedor en PostgreSQL, para el texto del mensaje
    if id_contenedor is None:
        return None
    with get_postgres_connection() as conexion, conexion.cursor() as cursor:
        cursor.execute("SELECT codigo_internacional FROM contenedor WHERE id_contenedor = %s",
                       (id_contenedor,))
        fila = cursor.fetchone()
        return fila[0] if fila else None


def textos_mensaje(alerta, codigo):  # arma el mensaje para internos y para el cliente; la usa notificar_alerta
    """(texto para internos, texto para el cliente)."""
    fecha = alerta.get("fecha")
    if fecha is not None:
        if fecha.tzinfo is None:
            fecha = fecha.replace(tzinfo=timezone.utc)
        fecha = fecha.astimezone(ZONA).strftime("%d/%m/%Y %H:%M")
    lugar = []
    if alerta.get("envio_id") is not None:
        lugar.append(f"envío {alerta['envio_id']}")
    if codigo:
        lugar.append(f"contenedor {codigo}")
    donde = (" en " + ", ".join(lugar)) if lugar else ""
    severidad = f" {alerta['severidad']}" if alerta.get("severidad") else ""
    tipo = alerta.get("tipo") or "sin tipo"
    descripcion = alerta.get("descripcion") or ""
    # Si la descripción ya empieza con el tipo ("Temperatura alta: valor 10…"),
    # no se repite el título.
    if descripcion.lower().startswith(tipo.lower()):
        base = f"Alerta{severidad}{donde}: {descripcion}".strip()
    else:
        base = f"Alerta{severidad}{donde}: {tipo}. {descripcion}".strip()
    # Nunca "None": cada dato se agrega solo si existe.
    extra_interno = [f"sensor {alerta['sensor_id']}"] if alerta.get("sensor_id") is not None else []
    extra_fecha = [fecha] if fecha else []
    interno = base + (f" ({', '.join(extra_interno + extra_fecha)})" if extra_interno + extra_fecha else "")
    cliente = base + (f" ({fecha})" if fecha else "")  # al cliente no se le muestra el número de sensor
    return interno, cliente


def notificar_alerta(alerta):  # manda los mensajes de una alerta nueva; la usa emitir_alerta
    """Mensajes de una alerta que todavía no los emitió. Devuelve la cantidad creada."""
    if alerta.get("mensajes_emitidos") is not False:
        return 0       # ya notificada, o anterior a la emisión de mensajes
    interno, cliente = textos_mensaje(alerta, codigo_contenedor(alerta.get("contenedor_id")))
    creados = 0
    for id_usuario, es_interno in destinatarios_alerta(alerta.get("envio_id")):  # internos activos y, si hay envío, los usuarios de su cliente
        if registrar_mensaje_alerta(alerta["_id"], id_usuario,  # el índice único evita mandar dos veces el mismo mensaje
                                    interno if es_interno else cliente):
            creados += 1
    marcar_mensajes_emitidos(alerta["_id"], creados)  # en MongoDB: la alerta ya no se vuelve a notificar
    logger.info("Alerta %s: %s mensaje(s) emitido(s)", alerta["_id"], creados)
    return creados


def emitir_alerta(**datos):  # guarda la alerta y manda los mensajes; la usan la detección, la revisión de sensores y la carga de ejemplo
    """Igual que registrar_alerta, más los mensajes. Devuelve la alerta.

    Si fallan los mensajes, la alerta queda guardada con mensajes_emitidos
    = False y se reintenta la próxima vez que se detecte.
    """
    alerta = registrar_alerta(**datos)  # en MongoDB, sin duplicar si ya existía
    try:
        alerta["mensajes_creados"] = notificar_alerta(alerta)
    except Exception:
        logger.exception("No se pudieron emitir los mensajes de la alerta %s", alerta.get("_id"))
        alerta["mensajes_creados"] = 0
    return alerta
