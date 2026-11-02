from datetime import datetime, timezone

from app.database.mongo_connection import get_mongo_database
from app.utils.errores import mensaje_error


COLECCION_EVENTOS = "eventos_logisticos"
COLECCION_PENDIENTES = "sync_pendientes"


# ------------------------------------------------------------------
# Eventos logísticos (fuente de verdad: MongoDB)
# ------------------------------------------------------------------

def insertar_evento(documento):
    db = get_mongo_database()
    resultado = db[COLECCION_EVENTOS].insert_one(documento)
    return str(resultado.inserted_id)


def listar_eventos_envio(id_envio):
    """Eventos de un envío en orden cronológico."""
    db = get_mongo_database()

    return list(
        db[COLECCION_EVENTOS]
        .find({"envio_id": int(id_envio)})
        .sort("fecha_hora", 1)
    )


def ultimo_evento_envio(id_envio, hasta=None):
    """Último evento del envío hasta ese momento (el vigente), o None."""
    hasta = hasta or datetime.now(timezone.utc)
    return get_mongo_database()[COLECCION_EVENTOS].find_one(
        {"envio_id": int(id_envio), "fecha_hora": {"$lte": hasta}},
        sort=[("fecha_hora", -1), ("_id", -1)],
    )


def buscar_eventos_por_id(ids_evento):
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


def listar_eventos_envios(ids_envio):
    """Eventos de varios envíos en orden cronológico."""
    if not ids_envio:
        return []

    db = get_mongo_database()

    return list(
        db[COLECCION_EVENTOS]
        .find({"envio_id": {"$in": [int(i) for i in ids_envio]}})
        .sort("fecha_hora", 1)
    )


def tipos_registrados(id_envio):
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

def registrar_pendiente_sync(id_envio, error):
    db = get_mongo_database()
    ahora = datetime.now(timezone.utc)

    db[COLECCION_PENDIENTES].update_one(
        {"envio_id": int(id_envio), "resuelto": False},
        {
            "$set": {
                "ultimo_error": mensaje_error(error)[:500],
                "fecha_actualizacion": ahora
            },
            "$inc": {"intentos": 1},
            "$setOnInsert": {
                "fecha_creacion": ahora,
                "resuelto": False
            }
        },
        upsert=True
    )


def listar_pendientes():
    db = get_mongo_database()

    return list(
        db[COLECCION_PENDIENTES]
        .find({"resuelto": False})
        .sort("fecha_creacion", 1)
    )


def resolver_pendientes_envio(id_envio):
    db = get_mongo_database()

    db[COLECCION_PENDIENTES].update_many(
        {"envio_id": int(id_envio), "resuelto": False},
        {"$set": {
            "resuelto": True,
            "fecha_resolucion": datetime.now(timezone.utc)
        }}
    )


# Pendientes de actualización de estado PostgreSQL después de registrar evento Mongo.
def registrar_pendiente_estado(id_envio, estado, evento_id, error,
                               fecha_entrega=None):
    db = get_mongo_database()
    ahora = datetime.now(timezone.utc)
    db["estado_pendientes"].update_one(
        {"evento_id": str(evento_id)},
        {"$set": {"envio_id": int(id_envio), "estado": estado,
                  "fecha_entrega": fecha_entrega,
                  "ultimo_error": mensaje_error(error)[:500], "resuelto": False,
                  "fecha_actualizacion": ahora},
         "$setOnInsert": {"fecha_creacion": ahora}},
        upsert=True,
    )


def listar_pendientes_estado():
    return list(get_mongo_database()["estado_pendientes"].find({"resuelto": False}))


def resolver_pendiente_estado(evento_id):
    get_mongo_database()["estado_pendientes"].update_one(
        {"evento_id": str(evento_id)},
        {"$set": {"resuelto": True, "fecha_resolucion": datetime.now(timezone.utc)}}
    )
