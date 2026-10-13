import os
from functools import lru_cache

from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB = os.getenv("MONGO_DB")


@lru_cache(maxsize=1)
def get_mongo_client():
    if not MONGO_URI:
        raise ValueError("Falta configurar MONGO_URI en .env")

    return MongoClient(
        MONGO_URI,
        tz_aware=True,
        serverSelectionTimeoutMS=5000
    )


def get_mongo_database():
    if not MONGO_DB:
        raise ValueError("Falta configurar MONGO_DB en .env")

    return get_mongo_client()[MONGO_DB]


def cerrar_conexion_mongo():
    if get_mongo_client.cache_info().currsize:
        get_mongo_client().close()
        get_mongo_client.cache_clear()


def probar_conexion_mongo():
    try:
        get_mongo_client().admin.command("ping")
        print("Conexión a MongoDB exitosa.")
    except Exception as error:
        print(f"Error al conectar con MongoDB: {error}")