$ErrorActionPreference = "Stop"
$compose = Join-Path $PSScriptRoot "..\docker-compose.integration.yml"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")

# Cada motor se inicializa solo si está vacío, se omite si ya coincide con el
# esquema completo esperado y se detiene ante cualquier estado parcial/distinto.
$pgCount = (& docker compose -f $compose exec -T postgres-integration psql -U integration -d logistica_poliglota_integration -Atc "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'").Trim()
if ($LASTEXITCODE -ne 0) { throw "No se pudo inspeccionar PostgreSQL de integración." }
if ($pgCount -eq "0") {
    Get-Content -Raw (Join-Path $root "scripts\postgresql_schema.sql") |
        docker compose -f $compose exec -T postgres-integration psql -v ON_ERROR_STOP=1 -U integration -d logistica_poliglota_integration
    if ($LASTEXITCODE -ne 0) { throw "Falló el esquema PostgreSQL; detener y conservar el stack." }
} elseif ($pgCount -ne "15") { throw "PostgreSQL tiene $pgCount tablas; no coincide con esquema vacío/completo. Se detiene." }

$mongoNames = (& docker compose -f $compose exec -T mongodb-integration mongosh --quiet --eval "db.getSiblingDB('logistica_poliglota_integration').getCollectionNames().sort().join(',')").Trim()
if ($LASTEXITCODE -ne 0) { throw "No se pudo inspeccionar MongoDB de integración." }
$expectedMongo = "alertas,eventos_logisticos,grupos_trabajo,mensajes,predicciones_riesgo"
if (-not $mongoNames) {
    docker compose -f $compose exec -T mongodb-integration mongosh --quiet --eval "var targetDatabaseName='logistica_poliglota_integration'" --file /integration-scripts/mongodb_schema.js
    if ($LASTEXITCODE -ne 0) { throw "Falló el esquema MongoDB; detener y conservar el stack." }
} elseif ($mongoNames -ne $expectedMongo) { throw "MongoDB no está vacío ni coincide con el esquema completo. Se detiene." }

$cassCount = (& docker compose -f $compose exec -T cassandra-integration cqlsh 127.0.0.1 9042 -e "SELECT count(*) FROM system_schema.tables WHERE keyspace_name='logistica_poliglota_integration' ALLOW FILTERING") | Out-String
if ($LASTEXITCODE -ne 0) { throw "No se pudo inspeccionar Cassandra de integración." }
if ($cassCount -match "(?m)^\s*0\s*$") {
    $cql = [System.IO.File]::ReadAllText((Join-Path $root "scripts\cassandra_schema.cql"))
    $cql = $cql.Replace("logistica_poliglota", "logistica_poliglota_integration")
    $cql | docker compose -f $compose exec -T cassandra-integration cqlsh 127.0.0.1 9042
    if ($LASTEXITCODE -ne 0) { throw "Falló el esquema Cassandra; detener y conservar el stack." }
} elseif ($cassCount -notmatch "(?m)^\s*3\s*$") { throw "Cassandra no está vacío ni contiene exactamente las 3 tablas esperadas. Se detiene." }

# La imagen Community permite una base de usuario predeterminada. Esta es una
# instancia/volumen/puerto exclusivos de integración; su base aislada se llama
# neo4j porque CREATE DATABASE no está disponible en esta edición.
$neoOutput = (& docker compose -f $compose exec -T neo4j-integration cypher-shell -u neo4j -p integration-only-not-a-real-secret -d neo4j --format plain "MATCH (n) RETURN count(n)") | Out-String
if ($LASTEXITCODE -ne 0) { throw "No se pudo inspeccionar la base Neo4j aislada." }
$neoCount = ($neoOutput.Trim() -split "\r?\n")[-1].Trim()
$neoConstraintOutput = (& docker compose -f $compose exec -T neo4j-integration cypher-shell -u neo4j -p integration-only-not-a-real-secret -d neo4j --format plain "SHOW CONSTRAINTS YIELD name RETURN name") | Out-String
if ($LASTEXITCODE -ne 0) { throw "No se pudieron inspeccionar las restricciones Neo4j." }
$neoConstraints = @("cliente_id_unique", "envio_id_unique", "tramo_id_unique", "vehiculo_id_unique", "contenedor_id_unique", "operador_nombre_unique", "ubicacion_nombre_unique")
$presentConstraints = @($neoConstraints | Where-Object { $neoConstraintOutput -match [regex]::Escape($_) })
if ($presentConstraints.Count -eq 0 -and $neoCount -eq "0") {
    docker compose -f $compose exec -T neo4j-integration cypher-shell -u neo4j -p integration-only-not-a-real-secret -d neo4j -f /integration-scripts/neo4j_schema.cypher
    if ($LASTEXITCODE -ne 0) { throw "Falló el esquema Neo4j; detener y conservar el stack." }
} elseif ($presentConstraints.Count -ne $neoConstraints.Count) { throw "Neo4j no está vacío ni contiene todas las restricciones esperadas. Se detiene." }

Write-Host "Los cuatro esquemas de integración se inicializaron en destinos vacíos verificados."
