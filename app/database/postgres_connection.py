import os
import psycopg
from dotenv import load_dotenv

load_dotenv()

POSTGRES_HOST = os.getenv("POSTGRES_HOST")
POSTGRES_PORT = os.getenv("POSTGRES_PORT")
POSTGRES_DB = os.getenv("POSTGRES_DB")
POSTGRES_USER = os.getenv("POSTGRES_USER")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD")


def get_postgres_connection():
    return psycopg.connect(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        dbname=POSTGRES_DB,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD
    )


def probar_conexion_postgres():
    conexion = None

    try:
        conexion = get_postgres_connection()

        with conexion.cursor() as cursor:
            cursor.execute("SELECT current_database();")
            base = cursor.fetchone()[0]

        print(f"Conexión a PostgreSQL exitosa. Base: {base}")

    except Exception as e:
        print(f"Error al conectar con PostgreSQL: {e}")

    finally:
        if conexion:
            conexion.close()