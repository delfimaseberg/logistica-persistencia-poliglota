from app.database.neo4j_connection import abrir_sesion_neo4j
from app.utils.validaciones_trazabilidad import normalizar_nombre_grafo


# Operador identificado por su id de PostgreSQL. "etiqueta" se mantiene por
# compatibilidad con las consultas de ruta.
_MERGE_OPERADOR = """
    MERGE (op:Operador {id_operador: $op.id_operador})
    SET op.razon_social = $op.razon_social,
        op.etiqueta = $op.razon_social,
        op.modalidades = $op.modalidades,
        op.estado = $op.estado
"""


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
                  -[r:UTILIZA_VEHICULO|SALE_DE|LLEGA_A|REALIZADO_POR]->()
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

        # Operador que realizó el tramo (PostgreSQL tramo.id_operador).
        if tramo.get("operador"):
            tx.run(_MERGE_OPERADOR + """
                WITH op
                MATCH (t:Tramo {id_tramo: $id_tramo})
                MERGE (t)-[:REALIZADO_POR]->(op)
            """, op=tramo["operador"], id_tramo=tramo["id_tramo"]).consume()

        # Operador actual del vehículo; puede haber cambiado.
        tx.run("""
            MATCH (:Vehiculo {id_vehiculo: $id_vehiculo})
                  -[r:OPERADO_POR]->(:Operador)
            DELETE r
        """, id_vehiculo=tramo["id_vehiculo"]).consume()

        if tramo.get("operador_vehiculo"):
            tx.run(_MERGE_OPERADOR + """
                WITH op
                MATCH (v:Vehiculo {id_vehiculo: $id_vehiculo})
                MERGE (v)-[:OPERADO_POR]->(op)
            """, op=tramo["operador_vehiculo"],
                id_vehiculo=tramo["id_vehiculo"]).consume()

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
    with abrir_sesion_neo4j() as sesion:
        sesion.execute_write(_sincronizar_tx, datos)


def _eliminar_tx(tx, id_envio):
    tx.run("""
        MATCH (e:Envio {id_envio: $id_envio})
        OPTIONAL MATCH (e)-[:TIENE_TRAMO]->(t:Tramo)
        DETACH DELETE t, e
    """, id_envio=id_envio).consume()


def eliminar_envio_grafo(id_envio):
    with abrir_sesion_neo4j() as sesion:
        sesion.execute_write(_eliminar_tx, id_envio)


def _ruta_tx(tx, id_envio):
    resultado = tx.run("""
        MATCH (e:Envio {id_envio: $id_envio})
        OPTIONAL MATCH (cl:Cliente)-[:REALIZA]->(e)
        OPTIONAL MATCH (e)-[:TIENE_TRAMO]->(t:Tramo)
        OPTIONAL MATCH (t)-[:SALE_DE]->(o:Ubicacion)
        OPTIONAL MATCH (t)-[:LLEGA_A]->(d:Ubicacion)
        OPTIONAL MATCH (t)-[:UTILIZA_VEHICULO]->(v:Vehiculo)
        OPTIONAL MATCH (t)-[:REALIZADO_POR]->(op:Operador)
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
    with abrir_sesion_neo4j() as sesion:
        return sesion.execute_read(_ruta_tx, id_envio)


# ------------------------------------------------------------------
# Operadores: red de relaciones y "quién llevó mi contenedor"
# ------------------------------------------------------------------

def _operadores_contenedor_tx(tx, id_contenedor, id_cliente):
    resultado = tx.run("""
        MATCH (cl:Cliente)-[:REALIZA]->(e:Envio)
              -[:UTILIZA_CONTENEDOR]->(:Contenedor {id_contenedor: $id_contenedor})
        WHERE $id_cliente IS NULL OR cl.id_cliente = $id_cliente
        MATCH (e)-[:TIENE_TRAMO]->(t:Tramo)
        OPTIONAL MATCH (t)-[:REALIZADO_POR]->(op:Operador)
        RETURN e.id_envio AS id_envio,
               cl.razon_social AS cliente,
               t.id_tramo AS id_tramo,
               t.medio_transporte AS medio,
               t.origen AS origen,
               t.destino AS destino,
               t.fecha_salida AS salida,
               op.id_operador AS id_operador,
               op.razon_social AS operador
        ORDER BY t.fecha_salida, t.id_tramo
    """, id_contenedor=id_contenedor, id_cliente=id_cliente)
    return [dict(fila) for fila in resultado]


def operadores_de_contenedor(id_contenedor, id_cliente=None):
    """Tramos y operadores que llevaron un contenedor.

    Con id_cliente, solo los envíos de ese cliente (un cliente nunca ve
    envíos de otro). Usa la asociación envío-contenedor vigente.
    """
    with abrir_sesion_neo4j() as sesion:
        return sesion.execute_read(
            _operadores_contenedor_tx, id_contenedor, id_cliente
        )


def _red_cliente_tx(tx, id_cliente):
    resultado = tx.run("""
        MATCH (cl:Cliente {id_cliente: $id_cliente})-[:REALIZA]->(e:Envio)
              -[:TIENE_TRAMO]->(:Tramo)-[:REALIZADO_POR]->(op:Operador)
        WITH op, collect(DISTINCT e.id_envio) AS envios
        OPTIONAL MATCH (otro:Cliente)-[:REALIZA]->(:Envio)
              -[:TIENE_TRAMO]->(:Tramo)-[:REALIZADO_POR]->(op)
        WHERE otro.id_cliente <> $id_cliente
        RETURN op.id_operador AS id_operador,
               op.razon_social AS operador,
               op.modalidades AS modalidades,
               envios,
               count(DISTINCT otro) AS otros_clientes
        ORDER BY size(envios) DESC, operador
    """, id_cliente=id_cliente)
    return [dict(fila) for fila in resultado]


def red_operadores_cliente(id_cliente):
    """Operadores que llevaron envíos del cliente.

    De los otros clientes que comparten operador solo se devuelve la
    cantidad, nunca sus nombres ni sus envíos.
    """
    with abrir_sesion_neo4j() as sesion:
        return sesion.execute_read(_red_cliente_tx, id_cliente)


def _eliminar_operadores_legados_tx(tx):
    resultado = tx.run("""
        MATCH (op:Operador)
        WHERE op.id_operador IS NULL
        DETACH DELETE op
        RETURN count(*) AS eliminados
    """)
    return resultado.single()["eliminados"]


def eliminar_operadores_legados():
    """Borra los :Operador creados desde el texto libre empresa_operadora.

    Son los nodos sin id_operador (identificados solo por nombre). Desde la
    migración 010 el operador se proyecta por su id de PostgreSQL.
    Devuelve la cantidad eliminada.
    """
    with abrir_sesion_neo4j() as sesion:
        return sesion.execute_write(_eliminar_operadores_legados_tx)
