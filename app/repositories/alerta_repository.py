
from datetime import datetime, timezone

from bson import ObjectId
from pymongo import ReturnDocument

from app.database.mongo_connection import get_mongo_database


def coleccion_alertas():
    coleccion = get_mongo_database()["alertas"]

    coleccion.create_index(
        [("clave_deteccion", 1)],
        unique=True,
        partialFilterExpression={
            "clave_deteccion": {"$type": "string"}
        },
        name="uq_alertas_clave_deteccion"
    )

    return coleccion


def registrar_alerta(
    sensor_id, contenedor_id, tipo, severidad,
    descripcion, lectura_id=None, envio_id=None
):
    coleccion = coleccion_alertas()

    documento = {
        "sensor_id": sensor_id,
        "contenedor_id": contenedor_id,
        "envio_id": envio_id,
        "evento_id": None,
        "tipo": tipo,
        "severidad": severidad,
        "descripcion": descripcion,
        "fecha": datetime.now(timezone.utc),
        "estado": "Activa",
        "lectura_id": str(lectura_id) if lectura_id is not None else None,
        "incidente_id": None
    }

    if lectura_id is None:
        resultado = coleccion.insert_one(documento)
        documento["_id"] = resultado.inserted_id
        return documento

    documento["clave_deteccion"] = (
        f"{sensor_id}:{lectura_id}:{tipo}"
    )

    return coleccion.find_one_and_update(
        {"clave_deteccion": documento["clave_deteccion"]},
        {"$setOnInsert": documento},
        upsert=True,
        return_document=ReturnDocument.AFTER
    )


def listar_alertas(estado=None, sensor_id=None):
    filtros = {}

    if estado:
        filtros["estado"] = estado

    if sensor_id is not None:
        filtros["sensor_id"] = sensor_id

    return list(
        coleccion_alertas()
        .find(filtros)
        .sort("fecha", -1)
        .limit(100)
    )


def actualizar_estado_alerta(id_alerta, estado):
    resultado = coleccion_alertas().update_one(
        {"_id": ObjectId(id_alerta)},
        {"$set": {"estado": estado}}
    )
    return resultado.matched_count > 0


def vincular_incidente_alerta(id_alerta, id_incidente):
    resultado = coleccion_alertas().update_one(
        {"_id": ObjectId(str(id_alerta))},
        {"$set": {"incidente_id": id_incidente}}
    )

    if resultado.matched_count != 1:
        raise RuntimeError(
            "No se encontró la alerta para vincular el incidente"
        )
