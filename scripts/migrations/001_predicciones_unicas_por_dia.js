// Ejecutar manualmente contra la base logistica_poliglota, con los
// procesos de predicción detenidos. No elimina registros históricos.
// Si hay duplicados del mismo envío y día local, aborta antes de escribir.
db = db.getSiblingDB("logistica_poliglota");

const coleccion = db.getCollection("predicciones_riesgo");

const registrosInvalidos = coleccion.aggregate([
    {
        $project: {
            tipo_envio: { $type: "$envio_id" },
            tipo_fecha: { $type: "$fecha_calculo" }
        }
    },
    {
        $match: {
            $or: [
                { tipo_envio: { $nin: ["int", "long"] } },
                { tipo_fecha: { $ne: "date" } }
            ]
        }
    },
    { $limit: 1 }
]).toArray();

if (registrosInvalidos.length > 0) {
    throw new Error(
        "Hay predicciones sin envio_id numérico o fecha_calculo válida; " +
        "no se aplicó la migración."
    );
}

const duplicados = coleccion.aggregate([
    {
        $project: {
            envio_id: 1,
            dia_calculo: {
                $dateToString: {
                    format: "%Y-%m-%d",
                    date: "$fecha_calculo",
                    timezone: "America/Argentina/Buenos_Aires"
                }
            }
        }
    },
    {
        $group: {
            _id: {
                envio_id: "$envio_id",
                dia_calculo: "$dia_calculo"
            },
            cantidad: { $sum: 1 },
            ids: { $push: "$_id" }
        }
    },
    { $match: { cantidad: { $gt: 1 } } },
    { $limit: 20 }
]).toArray();

if (duplicados.length > 0) {
    print("Se encontraron duplicados por envío y día (hora Argentina):");
    printjson(duplicados);
    throw new Error(
        "No se modificaron documentos ni se creó el índice. " +
        "Resolver los duplicados y volver a ejecutar la migración."
    );
}

coleccion.updateMany(
    {},
    [{
        $set: {
            dia_calculo: {
                $dateToString: {
                    format: "%Y-%m-%d",
                    date: "$fecha_calculo",
                    timezone: "America/Argentina/Buenos_Aires"
                }
            }
        }
    }]
);

// Conserva el índice usado por las consultas de historial, definido también
// en scripts/mongodb_schema.js. createIndex es idempotente para este índice.
coleccion.createIndex(
    { envio_id: 1, fecha_calculo: -1 },
    { name: "idx_predicciones_envio_fecha" }
);

coleccion.createIndex(
    { envio_id: 1, dia_calculo: 1 },
    {
        unique: true,
        name: "uq_predicciones_envio_dia"
    }
);

print("Índice único diario de predicciones creado correctamente.");
