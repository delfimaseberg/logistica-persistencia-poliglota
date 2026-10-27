# Pruebas de integración poliglota

Estas pruebas escriben exclusivamente en el stack `tp-bdd2-integration` y
fallan antes de ejecutar fixtures si no se confirma cada destino aislado.
No apuntan al `.env` habitual.

## Requisitos y ejecución

1. Docker Desktop en ejecución; puertos locales 15432, 27018, 19042, 17474 y
   17687 libres; entorno virtual `.venv` con `requirements.txt` y pytest.
2. Desde PowerShell en la raíz del repositorio:

   ```powershell
   .\scripts\start_integration.ps1
   .\scripts\initialize_integration.ps1
   .\scripts\run_integration_tests.ps1
   ```

3. La inicialización acepta solo destinos vacíos o que coincidan exactamente
   con el esquema esperado. PostgreSQL, MongoDB y Cassandra usan
   `logistica_poliglota_integration`. Neo4j Community no admite `CREATE DATABASE`;
   usa su base predeterminada `neo4j` dentro de un contenedor, volumen, red y
   puerto exclusivos. El inicializador se detiene ante estructuras parciales o
   inesperadas; no elimina ni recrea datos.
4. Para detener sin borrar los volúmenes:

   ```powershell
   docker compose -f .\docker-compose.integration.yml stop
   ```

   No usar `down -v`. Los contenedores y volúmenes de integración tienen nombres
   y redes de Compose propios y no comparten volúmenes con el stack habitual.

Las credenciales literales del compose son credenciales sintéticas exclusivas
del entorno local de integración; no corresponden a ningún entorno del proyecto.
No se almacena ni se lee el `.env` real para configurar las pruebas.

## Esquemas y límites

El orden es PostgreSQL, MongoDB, Cassandra y Neo4j. El script PostgreSQL crea
tablas sin `IF NOT EXISTS` y el MongoDB usa `createCollection`, por lo que ambos
requieren un destino vacío. Cassandra es reejecutable en DDL, pero el
inicializador puede reanudarse si encuentra el esquema completo y se detiene si
encuentra uno parcial. Neo4j verifica que su base aislada esté vacía y aplica
las restricciones `IF NOT EXISTS` en ella.

No se aplican migraciones financieras ni `001_predicciones_unicas_por_dia.js`.
La prueba de predicciones usa un envío sintético nuevo y no valida la resolución
de los duplicados históricos de la base habitual.
