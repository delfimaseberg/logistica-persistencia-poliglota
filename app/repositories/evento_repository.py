from datetime import datetime, timezone

from app.database.mongo_connection import get_mongo_database
from app.utils.errores import mensaje_error


COLECCION_EVENTOS = "eventos_logisticos"  # colecciones de MongoDB que usa este archivo
COLECCION_PENDIENTES = "sync_pendientes"


# ------------------------------------------------------------------
# Eventos logísticos (fuente de verdad: MongoDB)
# ------------------------------------------------------------------

def insertar_evento(documento):  # guarda un evento en MongoDB; la usan registrar evento y la carga de ejemplo
    db = get_mongo_database()
    resultado = db[COLECCION_EVENTOS].insert_one(documento)
    return str(resultado.inserted_id)


def listar_eventos_envio(id_envio):  # eventos de un envío; la usan historial, seguimiento, reportes y la fecha de entrega pendiente
    """Eventos de un envío en orden cronológico."""
    db = get_mongo_database()

    return list(
        db[COLECCION_EVENTOS]
        .find({"envio_id": int(id_envio)})
        .sort("fecha_hora", 1)
    )


def ultimo_evento_envio(id_envio, hasta=None):  # evento vigente del envío; la usa registrar_alerta
    """Último evento del envío hasta ese momento (el vigente), o None."""
    hasta = hasta or datetime.now(timezone.utc)
    return get_mongo_database()[COLECCION_EVENTOS].find_one(
        {"envio_id": int(id_envio), "fecha_hora": {"$lte": hasta}},  # el más nuevo que no sea futuro
        sort=[("fecha_hora", -1), ("_id", -1)],
    )


def buscar_eventos_por_id(ids_evento):  # varios eventos por ID; la usa consultar alertas
    """{id en texto: evento} para mostrar varios eventos de una vez."""
    from bson import ObjectId
    from bson.errors import InvalidId
    validos = []
    for id_evento in ids_evento:
        try:
            validos.append(ObjectId(str(id_evento)))
        except (InvalidId, TypeError):
            continue
    if not validos:
        return {}
    cursor = get_mongo_database()[COLECCION_EVENTOS].find({"_id": {"$in": validos}})
    return {str(evento["_id"]): evento for evento in cursor}


def listar_eventos_envios(ids_envio):  # eventos de varios envíos; la usan el recorrido de un contenedor y reportes
    """Eventos de varios envíos en orden cronológico."""
    if not ids_envio:
        return []

    db = get_mongo_database()

    return list(
        db[COLECCION_EVENTOS]
        .find({"envio_id": {"$in": [int(i) for i in ids_envio]}})
        .sort("fecha_hora", 1)
    )


def tipos_registrados(id_envio):  # tipos de evento que ya tiene el envío; la usa registrar evento
    db = get_mongo_database()

    return set(
        db[COLECCION_EVENTOS].distinct(
            "tipo",
            {"envio_id": int(id_envio)}
        )
    )


# ------------------------------------------------------------------
# Pendientes de sincronización PostgreSQL -> Neo4j
# Se guardan de forma persistente para poder reintentarlos.
# ------------------------------------------------------------------

def registrar_pendiente_sync(id_envio, error):  # anota en MongoDB un envío que no se pudo copiar a Neo4j; la usa sincronizacion_service
    db = get_mongo_database()
    ahora = datetime.now(timezone.utc)

    db[COLECCION_PENDIENTES].update_one(
        {"envio_id": int(id_envio), "resuelto": False},  # un solo pendiente abierto por envío
        {
            "$set": {
                "ultimo_error": mensaje_error(error)[:500],
                "fecha_actualizacion": ahora
            },
            "$inc": {"intentos": 1},  # cuenta los reintentos
            "$setOnInsert": {
                "fecha_creacion": ahora,
                "resuelto": False
            }
        },
        upsert=True
    )


def listar_pendientes():  # pendientes de Neo4j sin resolver; la usan reparar_pendientes y la opción 6
    db = get_mongo_database()

    return list(
        db[COLECCION_PENDIENTES]
        .find({"resuelto": False})
        .sort("fecha_creacion", 1)
    )


def resolver_pendientes_envio(id_envio):  # cierra los pendientes de un envío ya sincronizado
    db = get_mongo_database()

    db[COLECCION_PENDIENTES].update_many(
        {"envio_id": int(id_envio), "resuelto": False},
        {"$set": {
            "resuelto": True,
            "fecha_resolucion": datetime.now(timezone.utc)
        }}
    )


# Pendientes de actualización de estado PostgreSQL después de registrar evento Mongo.
def registrar_pendiente_estado(id_envio, estado, evento_id, error,  # anota un cambio de estado que no llegó a PostgreSQL; la usa registrar evento
                               fecha_entrega=None):
    db = get_mongo_database()
    ahora = datetime.now(timezone.utc)
    db["estado_pendientes"].update_one(
        {"evento_id": str(evento_id)},  # uno por evento
        {"$set": {"envio_id": int(id_envio), "estado": estado,
                  "fecha_entrega": fecha_entrega,
                  "ultimo_error": mensaje_error(error)[:500], "resuelto": False,
                  "fecha_actualizacion": ahora},
         "$setOnInsert": {"fecha_creacion": ahora}},
        upsert=True,
    )


def listar_pendientes_estado():  # cambios de estado sin aplicar; la usa la opción 6 de trazabilidad
    return list(get_mongo_database()["estado_pendientes"].find({"resuelto": False}))


def resolver_pendiente_estado(evento_id):  # marca resuelto un cambio de estado ya aplicado
    get_mongo_database()["estado_pendientes"].update_one(
        {"evento_id": str(evento_id)},
        {"$set": {"resuelto": True, "fecha_resolucion": datetime.now(timezone.utc)}}
    )
