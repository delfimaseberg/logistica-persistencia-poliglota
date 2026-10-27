def main():
    from app.database.postgres_connection import probar_conexion_postgres
    from app.database.mongo_connection import probar_conexion_mongo
    from app.database.cassandra_connection import probar_conexion_cassandra
    from app.database.neo4j_connection import probar_conexion_neo4j

    print("Probando PostgreSQL...")
    probar_conexion_postgres()

    print("\nProbando MongoDB...")
    probar_conexion_mongo()

    print("\nProbando Cassandra...")
    probar_conexion_cassandra()

    print("\nProbando Neo4j...")
    probar_conexion_neo4j()


if __name__ == "__main__":
    main()
