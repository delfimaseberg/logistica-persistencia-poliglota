import os
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")


def get_neo4j_driver():
    return GraphDatabase.driver(
        NEO4J_URI,
        auth=(NEO4J_USER, NEO4J_PASSWORD)
    )


def probar_conexion_neo4j():
    driver = None

    try:
        driver = get_neo4j_driver()
        driver.verify_connectivity()
        print("Conexión a Neo4j exitosa.")
    except Exception as e:
        print(f"Error al conectar con Neo4j: {e}")
    finally:
        if driver:
            driver.close()