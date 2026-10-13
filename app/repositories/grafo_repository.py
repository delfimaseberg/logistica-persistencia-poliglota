from app.database.neo4j_connection import obtener_driver_neo4j
from app.utils.validaciones_trazabilidad import normalizar_nombre_grafo


def _sincronizar_tx(tx, datos):
    """Proyecta un envío completo. Es idempotente (usa MERGE)."""
    envio = datos["envio"]
    cliente = datos["cliente"]
    tramos = datos["tramos"]
    contenedores = datos["contenedores"]
    id_envio = envio["id_envio"]

    # Cliente y envío. Si el envío cambió de cliente se elimina la
    # relación anterior.
    tx.run("""
        MERGE (c:Cliente {id_cliente: $cliente.id_cliente})
        SET c.razon_social = $cliente.razon_social,
            c.pais = $cliente.pais
        MERGE (e:Envio {id_envio: $envio.id_envio})
        SET e.estado = $envio.estado,
            e.prioridad = $envio.prioridad,
            e.origen = $envio.origen,
            e.destino = $envio.destino,
            e.fecha_creacion = $envio.fecha_creacion
        WITH c, e
        OPTIONAL MATCH (otro:Cliente)-[viejo:REALIZA]->(e)
        WHERE otro.id_cliente <> $cliente.id_cliente
        DELETE viejo
        MERGE (c)-[:REALIZA]->(e)
    """, cliente=cliente, envio=envio).consume()

    # Tramos que ya no existen en PostgreSQL.
    tx.run("""
        MATCH (:Envio {id_envio: $id_envio})-[:TIENE_TRAMO]->(t:Tramo)
        WHERE NOT t.id_tramo IN $ids
        DETACH DELETE t
    """, id_envio=id_envio,
        ids=[t["id_tramo"] for t in tramos]).consume()

    for tramo in tramos:
        origen_norm = normalizar_nombre_grafo(tramo["origen"])
        destino_norm = normalizar_nombre_grafo(tramo["destino"])
        operador_norm = normalizar_nombre_grafo(
            tramo["empresa_operadora"]
        )

        tx.run("""
            MATCH (e:Envio {id_envio: $id_envio})
            MERGE (t:Tramo {id_tramo: $t.id_tramo})
            SET t.medio_transporte = $t.medio_transporte,
                t.origen = $t.origen,
                t.destino = $t.destino,
                t.fecha_salida = $t.fecha_salida,
                t.fecha_estimada_llegada = $t.fecha_estimada_llegada
            MERGE (e)-[:TIENE_TRAMO]->(t)
        """, id_envio=id_envio, t=tramo).consume()

        # Relaciones del tramo que pudieron cambiar.
        tx.run("""
            MATCH (:Tramo {id_tramo: $id_tramo})
                  -[r:UTILIZA_VEHICULO|SALE_DE|LLEGA_A]->()
            DELETE r
        """, id_tramo=tramo["id_tramo"]).consume()

        tx.run("""
            MATCH (t:Tramo {id_tramo: $t.id_tramo})
            MERGE (v:Vehiculo {id_vehiculo: $t.id_vehiculo})
            SET v.identificacion = $t.identificacion,
                v.tipo = $t.tipo_vehiculo
            MERGE (t)-[:UTILIZA_VEHICULO]->(v)
            MERGE (o:Ubicacion {nombre: $origen_norm})
            ON CREATE SET o.etiqueta = $t.origen
            MERGE (t)-[:SALE_DE]->(o)
            MERGE (d:Ubicacion {nombre: $destino_norm})
            ON CREATE SET d.etiqueta = $t.destino
            MERGE (t)-[:LLEGA_A]->(d)
        """, t=tramo, origen_norm=origen_norm,
            destino_norm=destino_norm).consume()

        # El operador del vehículo puede haber cambiado.
        tx.run("""
            MATCH (:Vehiculo {id_vehiculo: $id_vehiculo})
                  -[r:OPERADO_POR]->(:Operador)
            DELETE r
        """, id_vehiculo=tramo["id_vehiculo"]).consume()

        if operador_norm:
            tx.run("""
                MATCH (v:Vehiculo {id_vehiculo: $id_vehiculo})
                MERGE (op:Operador {nombre: $operador_norm})
                ON CREATE SET op.etiqueta = $etiqueta
                MERGE (v)-[:OPERADO_POR]->(op)
            """, id_vehiculo=tramo["id_vehiculo"],
                operador_norm=operador_norm,
                etiqueta=tramo["empresa_operadora"].strip()).consume()

    # Contenedores del envío.
    tx.run("""
        MATCH (:Envio {id_envio: $id_envio})-[r:UTILIZA_CONTENEDOR]->()
        DELETE r
    """, id_envio=id_envio).consume()

    if contenedores:
        tx.run("""
            MATCH (e:Envio {id_envio: $id_envio})
            UNWIND $contenedores AS c
            MERGE (k:Contenedor {id_contenedor: c.id_contenedor})
            SET k.codigo = c.codigo
            MERGE (e)-[:UTILIZA_CONTENEDOR]->(k)
        """, id_envio=id_envio, contenedores=contenedores).consume()


def sincronizar_envio_grafo(datos):
    with obtener_driver_neo4j().session() as sesion:
        sesion.execute_write(_sincronizar_tx, datos)


def _eliminar_tx(tx, id_envio):
    tx.run("""
        MATCH (e:Envio {id_envio: $id_envio})
        OPTIONAL MATCH (e)-[:TIENE_TRAMO]->(t:Tramo)
        DETACH DELETE t, e
    """, id_envio=id_envio).consume()


def eliminar_envio_grafo(id_envio):
    with obtener_driver_neo4j().session() as sesion:
        sesion.execute_write(_eliminar_tx, id_envio)


def _ruta_tx(tx, id_envio):
    resultado = tx.run("""
        MATCH (e:Envio {id_envio: $id_envio})
        OPTIONAL MATCH (cl:Cliente)-[:REALIZA]->(e)
        OPTIONAL MATCH (e)-[:TIENE_TRAMO]->(t:Tramo)
        OPTIONAL MATCH (t)-[:SALE_DE]->(o:Ubicacion)
        OPTIONAL MATCH (t)-[:LLEGA_A]->(d:Ubicacion)
        OPTIONAL MATCH (t)-[:UTILIZA_VEHICULO]->(v:Vehiculo)
        OPTIONAL MATCH (v)-[:OPERADO_POR]->(op:Operador)
        RETURN e.id_envio AS id_envio,
               e.estado AS estado,
               e.origen AS origen_envio,
               e.destino AS destino_envio,
               cl.razon_social AS cliente,
               t.id_tramo AS id_tramo,
               t.medio_transporte AS medio,
               t.fecha_salida AS salida,
               t.fecha_estimada_llegada AS llegada,
               o.etiqueta AS origen_tramo,
               d.etiqueta AS destino_tramo,
               v.identificacion AS vehiculo,
               op.etiqueta AS operador
        ORDER BY t.fecha_salida, t.id_tramo
    """, id_envio=id_envio)

    return [dict(fila) for fila in resultado]


def obtener_ruta_envio(id_envio):
    """Filas de la ruta (una por tramo). Lista vacía si el envío no está
    en el grafo.
    """
    with obtener_driver_neo4j().session() as sesion:
        return sesion.execute_read(_ruta_tx, id_envio)
