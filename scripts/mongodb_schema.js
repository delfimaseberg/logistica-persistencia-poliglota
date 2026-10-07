// =========================================================
// LOGÍSTICA POLÍGLOTA
// Modelo físico MongoDB
// =========================================================

// Seleccionar la base de datos
db = db.getSiblingDB("logistica_poliglota");


// =========================
// EVENTOS LOGÍSTICOS
// =========================
db.createCollection("eventos_logisticos");

db.eventos_logisticos.createIndex(
    { envio_id: 1, fecha_hora: -1 },
    { name: "idx_eventos_envio_fecha" }
);


// =========================
// ALERTAS
// =========================
db.createCollection("alertas");

db.alertas.createIndex(
    { sensor_id: 1, fecha: -1 },
    { name: "idx_alertas_sensor_fecha" }
);


// =========================
// MENSAJES
// =========================
db.createCollection("mensajes");

db.mensajes.createIndex(
    { destinatario_id: 1, fecha_hora: -1 },
    { name: "idx_mensajes_destinatario_fecha" }
);

db.mensajes.createIndex(
    { grupo_id: 1, fecha_hora: -1 },
    { name: "idx_mensajes_grupo_fecha" }
);


// =========================
// GRUPOS DE TRABAJO
// =========================
db.createCollection("grupos_trabajo");

db.grupos_trabajo.createIndex(
    { "miembros.usuario_id": 1 },
    { name: "idx_grupos_miembros" }
);


// =========================
// PREDICCIONES DE RIESGO
// =========================
db.createCollection("predicciones_riesgo");

db.predicciones_riesgo.createIndex(
    { envio_id: 1, fecha_calculo: -1 },
    { name: "idx_predicciones_envio_fecha" }
);

print("Estructura MongoDB creada correctamente.");