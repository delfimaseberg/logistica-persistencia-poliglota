# Instalación de Trazabilidad

Este paquete es una **copia completa del proyecto de referencia** con el módulo integrado. Para conservar tus cambios locales, copiá **solo los archivos enumerados abajo** desde este ZIP a tu carpeta `Tp_bdd2` (mismas rutas).

Archivos a copiar: `app/utils/logger.py`, `app/utils/validaciones_trazabilidad.py`, `app/database/mongo_connection.py`, `app/database/neo4j_connection.py`, `app/repositories/evento_repository.py`, `app/repositories/trazabilidad_repository.py`, `app/repositories/grafo_repository.py`, `app/repositories/recorrido_repository.py`, `app/services/sincronizacion_service.py`, `app/services/trazabilidad_service.py`, `app/services/envio_service.py`, `app/services/tramo_service.py`, `app/services/envio_contenedor_service.py`, `app/ui/menu_trazabilidad.py`, `app/ui/menu_principal.py`, `scripts/mongodb_schema.js`, `tests/test_trazabilidad.py`, `conftest.py`.

No copies `.env` ni reemplaces todo el proyecto. Ejecutá `python -m compileall -q app`, `python -m pytest tests/test_trazabilidad.py -q`, `python main.py`. Ejecutá `scripts/mongodb_schema.js` con mongosh contra tu MongoDB, si no lo ejecutaste. Si no tenés pytest: `python -m pip install pytest`.

Requiere MongoDB, Neo4j, PostgreSQL y Cassandra iniciados. El script de Mongo añade colecciones/índices; no hace cambios al esquema de PostgreSQL. La tabla PostgreSQL `evento_logistico` creada previamente no se utiliza.

**Limitaciones:** no hay transacciones distribuidas entre MongoDB y PostgreSQL; se guarda pendiente para reintento. La reconstrucción de contenedores usa asociaciones actuales y no registra fechas históricas de vinculación. La resincronización masiva reconstruye envíos actuales pero no purga automáticamente envíos obsoletos del grafo; eliminaciones hechas desde el servicio sí disparan reconciliación.
