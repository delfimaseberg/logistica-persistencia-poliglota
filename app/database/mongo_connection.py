import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB = os.getenv("MONGO_DB")


def get_mongo_database():
    client = MongoClient(MONGO_URI)
    return client[MONGO_DB]


def probar_conexion_mongo():
    try:
        client = MongoClient(MONGO_URI)
        client.admin.command("ping")
        print("Conexión a MongoDB exitosa.")
        client.close()
    except Exception as e:
        print(f"Error al conectar con MongoDB: {e}")