import os
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE")

_driver = None


def get_neo4j_driver():
    """Crea un driver de Neo4j."""
    if not all((NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)):
        raise ValueError("Falta configurar Neo4j en el archivo .env")

    return GraphDatabase.driver(
        NEO4J_URI,
        auth=(NEO4J_USER, NEO4J_PASSWORD)
    )


def obtener_driver_neo4j():
    """Reutiliza el mismo driver para las operaciones del grafo."""
    global _driver

    if _driver is None:
        _driver = get_neo4j_driver()

    return _driver


def abrir_sesion_neo4j():
    # Abre la base configurada; sin NEO4J_DATABASE usa la predeterminada.
    driver = obtener_driver_neo4j()
    if NEO4J_DATABASE:
        return driver.session(database=NEO4J_DATABASE)
    return driver.session()


def probar_conexion_neo4j():
    driver = None

    try:
        driver = get_neo4j_driver()
        driver.verify_connectivity()
        print("Conexión a Neo4j exitosa.")
    except Exception as error:
        print(f"Error al conectar con Neo4j: {error}")
    finally:
        if driver is not None:
            driver.close()
