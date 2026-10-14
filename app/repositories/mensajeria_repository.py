from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId

from app.database.postgres_connection import get_postgres_connection
from app.database.mongo_connection import get_mongo_database


def obtener_usuario_activo(id_usuario):
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT id_usuario, nombre, apellido, email
                FROM usuario
                WHERE id_usuario = %s
                  AND estado = 'ACTIVO'
            """, (id_usuario,))
            return cursor.fetchone()


def obtener_usuarios_activos():
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT id_usuario, nombre, apellido, email
                FROM usuario
                WHERE estado = 'ACTIVO'
                ORDER BY nombre, apellido
            """)
            return cursor.fetchall()


def coleccion_mensajes():
    coleccion = get_mongo_database()["mensajes"]
    coleccion.create_index(
        [("destinatario_id", 1), ("fecha_hora", -1)],
        name="idx_mensajes_destinatario_fecha"
    )
    coleccion.create_index(
        [("grupo_id", 1), ("fecha_hora", -1)],
        name="idx_mensajes_grupo_fecha"
    )
    coleccion.create_index(
        [("remitente_id", 1), ("fecha_hora", -1)],
        name="idx_mensajes_remitente_fecha"
    )
    return coleccion


def coleccion_grupos():
    coleccion = get_mongo_database()["grupos_trabajo"]
    coleccion.create_index(
        [("miembros.usuario_id", 1)],
        name="idx_grupos_miembros"
    )
    return coleccion


def registrar_mensaje_privado(remitente_id, destinatario_id, contenido):
    documento = {
        "tipo": "Privado",
        "remitente_id": remitente_id,
        "destinatario_id": destinatario_id,
        "grupo_id": None,
        "contenido": contenido,
        "fecha_hora": datetime.now(timezone.utc),
        "leido": False
    }

    resultado = coleccion_mensajes().insert_one(documento)
    return str(resultado.inserted_id)


def obtener_bandeja_entrada(id_usuario):
    return list(
        coleccion_mensajes()
        .find({
            "tipo": "Privado",
            "destinatario_id": id_usuario
        })
        .sort("fecha_hora", -1)
        .limit(50)
    )


def obtener_mensajes_enviados(id_usuario):
    return list(
        coleccion_mensajes()
        .find({
            "tipo": "Privado",
            "remitente_id": id_usuario
        })
        .sort("fecha_hora", -1)
        .limit(50)
    )


def obtener_conversacion(id_usuario, otro_usuario):
    filtro = {
        "tipo": "Privado",
        "$or": [
            {
                "remitente_id": id_usuario,
                "destinatario_id": otro_usuario
            },
            {
                "remitente_id": otro_usuario,
                "destinatario_id": id_usuario
            }
        ]
    }

    mensajes = list(
        coleccion_mensajes()
        .find(filtro)
        .sort("fecha_hora", -1)
        .limit(50)
    )

    return list(reversed(mensajes))


def marcar_mensaje_leido(id_mensaje, destinatario_id):
    try:
        identificador = ObjectId(id_mensaje)
    except (InvalidId, TypeError):
        return False

    resultado = coleccion_mensajes().update_one(
        {
            "_id": identificador,
            "tipo": "Privado",
            "destinatario_id": destinatario_id
        },
        {
            "$set": {
                "leido": True,
                "fecha_lectura": datetime.now(timezone.utc)
            }
        }
    )

    return resultado.matched_count > 0


def contar_mensajes_no_leidos(id_usuario):
    return coleccion_mensajes().count_documents({
        "tipo": "Privado",
        "destinatario_id": id_usuario,
        "leido": False
    })


def crear_grupo(nombre, descripcion, creador_id):
    documento = {
        "nombre": nombre,
        "descripcion": descripcion,
        "creador_id": creador_id,
        "fecha_creacion": datetime.now(timezone.utc),
        "estado": "Activo",
        "miembros": [
            {
                "usuario_id": creador_id,
                "rol": "Administrador",
                "fecha_ingreso": datetime.now(timezone.utc)
            }
        ]
    }

    resultado = coleccion_grupos().insert_one(documento)
    return str(resultado.inserted_id)


def buscar_grupo(id_grupo):
    try:
        identificador = ObjectId(id_grupo)
    except (InvalidId, TypeError):
        return None

    return coleccion_grupos().find_one({
        "_id": identificador,
        "estado": "Activo"
    })


def listar_grupos_usuario(id_usuario):
    return list(
        coleccion_grupos()
        .find({
            "estado": "Activo",
            "miembros.usuario_id": id_usuario
        })
        .sort("nombre", 1)
    )


def usuario_es_miembro(grupo, id_usuario):
    return any(
        miembro.get("usuario_id") == id_usuario
        for miembro in grupo.get("miembros", [])
    )


def agregar_miembro_grupo(id_grupo, id_usuario):
    grupo = buscar_grupo(id_grupo)

    if grupo is None:
        return False

    if usuario_es_miembro(grupo, id_usuario):
        return False

    resultado = coleccion_grupos().update_one(
        {
            "_id": grupo["_id"],
            "estado": "Activo",
            "miembros.usuario_id": {"$ne": id_usuario}
        },
        {
            "$push": {
                "miembros": {
                    "usuario_id": id_usuario,
                    "rol": "Miembro",
                    "fecha_ingreso": datetime.now(timezone.utc)
                }
            }
        }
    )

    return resultado.modified_count > 0


def registrar_mensaje_grupo(remitente_id, id_grupo, contenido):
    grupo = buscar_grupo(id_grupo)

    if grupo is None:
        raise ValueError("El grupo no existe.")

    if not usuario_es_miembro(grupo, remitente_id):
        raise PermissionError("No pertenecés a este grupo.")

    documento = {
        "tipo": "Grupo",
        "remitente_id": remitente_id,
        "destinatario_id": None,
        "grupo_id": str(grupo["_id"]),
        "contenido": contenido,
        "fecha_hora": datetime.now(timezone.utc)
    }

    resultado = coleccion_mensajes().insert_one(documento)
    return str(resultado.inserted_id)


def obtener_mensajes_grupo(id_grupo, id_usuario):
    grupo = buscar_grupo(id_grupo)

    if grupo is None:
        raise ValueError("El grupo no existe.")

    if not usuario_es_miembro(grupo, id_usuario):
        raise PermissionError("No pertenecés a este grupo.")

    mensajes = list(
        coleccion_mensajes()
        .find({
            "tipo": "Grupo",
            "grupo_id": str(grupo["_id"])
        })
        .sort("fecha_hora", -1)
        .limit(50)
    )

    return list(reversed(mensajes))