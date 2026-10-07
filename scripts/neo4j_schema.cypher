// =========================================================
// LOGÍSTICA POLÍGLOTA
// Modelo físico Neo4j
// =========================================================


// =========================
// RESTRICCIONES DE UNICIDAD
// =========================

CREATE CONSTRAINT cliente_id_unique IF NOT EXISTS
FOR (c:Cliente)
REQUIRE c.id_cliente IS UNIQUE;

CREATE CONSTRAINT envio_id_unique IF NOT EXISTS
FOR (e:Envio)
REQUIRE e.id_envio IS UNIQUE;

CREATE CONSTRAINT tramo_id_unique IF NOT EXISTS
FOR (t:Tramo)
REQUIRE t.id_tramo IS UNIQUE;

CREATE CONSTRAINT vehiculo_id_unique IF NOT EXISTS
FOR (v:Vehiculo)
REQUIRE v.id_vehiculo IS UNIQUE;

CREATE CONSTRAINT contenedor_id_unique IF NOT EXISTS
FOR (c:Contenedor)
REQUIRE c.id_contenedor IS UNIQUE;

CREATE CONSTRAINT operador_nombre_unique IF NOT EXISTS
FOR (o:Operador)
REQUIRE o.nombre IS UNIQUE;

CREATE CONSTRAINT ubicacion_nombre_unique IF NOT EXISTS
FOR (u:Ubicacion)
REQUIRE u.nombre IS UNIQUE;