$ErrorActionPreference = "Stop"
$compose = Join-Path $PSScriptRoot "..\docker-compose.integration.yml"
$ports = @(15432, 27018, 19042, 17474, 17687)

foreach ($port in $ports) {
    $listener = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue
    if ($listener) {
        throw "El puerto de integración $port ya está ocupado. No se inició Docker."
    }
}

docker compose -f $compose up -d --wait --wait-timeout 600
if ($LASTEXITCODE -ne 0) {
    throw "Docker Compose no pudo iniciar el stack de integración."
}

docker compose -f $compose ps
if ($LASTEXITCODE -ne 0) {
    throw "No se pudo verificar el stack de integración."
}
