
from datetime import datetime, timezone

from bson import ObjectId

from app.database.mongo_connection import get_mongo_database
from app.repositories.evento_repository import ultimo_evento_envio


def coleccion_alertas():  # colección alertas de MongoDB; la usan todas las funciones de acá
    coleccion = get_mongo_database()["alertas"]

    coleccion.create_index(  # índice único por clave_deteccion: la misma alerta no se guarda dos veces
        [("clave_deteccion", 1)],
        unique=True,
        partialFilterExpression={
            "clave_deteccion": {"$type": "string"}
        },
        name="uq_alertas_clave_deteccion"
    )

    return coleccion



def registrar_alerta(  # guarda una alerta Activa si no existía; la usa emitir_alerta
    sensor_id,
    contenedor_id,
    tipo,
    severidad,
    descripcion,
    lectura_id=None,
    envio_id=None,
    clave_deteccion=None,
):
    coleccion = coleccion_alertas()
    ahora = datetime.now(timezone.utc)

    # Evento logístico vigente del envío al momento de la detección.
    evento = ultimo_evento_envio(envio_id, ahora) if envio_id is not None else None  # último evento del envío en MongoDB

    documento = {
        "sensor_id": sensor_id,
        "contenedor_id": contenedor_id,
        "envio_id": envio_id,
        "evento_id": str(evento["_id"]) if evento else None,
        "tipo": tipo,
        "severidad": severidad,
        "descripcion": descripcion,
        "fecha": ahora,
        "estado": "Activa",
        "lectura_id": (
            str(lectura_id) if lectura_id is not None else None
        ),
        "incidente_id": None,
        # Las alertas nuevas emiten mensajes (alertas_service.emitir_alerta);
        # las anteriores a este campo no lo tienen y no se notifican.
        "mensajes_emitidos": False,
    }

    if clave_deteccion is None and lectura_id is not None:
        clave_deteccion = f"{sensor_id}:{lectura_id}:{tipo}"  # clave: sensor, lectura y tipo

    if clave_deteccion is None:
        resultado = coleccion.insert_one(documento)
        documento["_id"] = resultado.inserted_id
        documento["nueva"] = True
        return documento

    documento["clave_deteccion"] = clave_deteccion

    resultado = coleccion.update_one(  # upsert con $setOnInsert: si ya existe, no la toca
        {"clave_deteccion": clave_deteccion},
        {"$setOnInsert": documento},
        upsert=True,
    )
    alerta = coleccion.find_one({"clave_deteccion": clave_deteccion})
    # "nueva" no se guarda: indica si esta llamada la creó.
    alerta["nueva"] = resultado.upserted_id is not None
    return alerta


def marcar_mensajes_emitidos(id_alerta, cantidad):  # anota que ya se mandaron los mensajes; la usa notificar_alerta
    coleccion_alertas().update_one(
        {"_id": ObjectId(str(id_alerta))},
        {"$set": {"mensajes_emitidos": True, "mensajes_cantidad": cantidad}},
    )


def atender_alertas_de_contenedores(tipos_regex, ids_contenedores, nota, aplicar=False):  # pasa a Atendida alertas viejas de contenedores; la usa la migración 015
    """Pasa a Atendida las alertas activas de esos tipos y contenedores.

    Sin aplicar=True solo cuenta. No borra nada. Devuelve la cantidad.
    """
    filtro = {
        "tipo": {"$regex": tipos_regex},
        "estado": "Activa",
        "contenedor_id": {"$in": [int(i) for i in ids_contenedores]},
    }
    coleccion = coleccion_alertas()
    if not aplicar:
        return coleccion.count_documents(filtro)
    resultado = coleccion.update_many(
        filtro,
        {"$set": {"estado": "Atendida", "nota_atencion": nota,
                  "fecha_atencion": datetime.now(timezone.utc)}},
    )
    return resultado.modified_count


def listar_alertas(estado=None, sensor_id=None):  # las últimas 100 alertas con filtros opcionales; la usan consultar y atender alertas
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


def actualizar_estado_alerta(id_alerta, estado):  # cambia el estado de una alerta; la usa atender alerta
    resultado = coleccion_alertas().update_one(
        {"_id": ObjectId(id_alerta)},
        {"$set": {"estado": estado}}
    )
    return resultado.matched_count > 0


def vincular_incidente_alerta(id_alerta, id_incidente):  # guarda en la alerta el ID del incidente de PostgreSQL; la usa procesar_incidente_de_alerta
    resultado = coleccion_alertas().update_one(
        {"_id": ObjectId(str(id_alerta))},
        {"$set": {"incidente_id": id_incidente}}
    )

    if resultado.matched_count != 1:
        raise RuntimeError(
            "No se encontró la alerta para vincular el incidente"
        )


def listar_alertas_contenedores(ids_contenedores, desde=None, hasta=None):  # alertas de varios contenedores en un período; la usa el reporte cobrable de incidentes
    """Alertas de un conjunto de contenedores (reportes por cliente).

    desde/hasta son datetimes con zona horaria (hasta excluido).
    """
    if not ids_contenedores:
        return []
    filtro = {"contenedor_id": {"$in": [int(i) for i in ids_contenedores]}}
    rango = {}
    if desde is not None:
        rango["$gte"] = desde
    if hasta is not None:
        rango["$lt"] = hasta
    if rango:
        filtro["fecha"] = rango
    return list(get_mongo_database()["alertas"].find(filtro).sort("fecha", 1))
