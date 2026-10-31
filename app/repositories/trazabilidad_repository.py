from app.database.postgres_connection import get_postgres_connection


def actualizar_estado_envio(id_envio, estado, fecha_entrega=None):
    """Actualiza el estado por un evento logístico.

    Pasar a Entregado exige la fecha real de entrega (la del evento) y se
    guarda junto con el estado. Un envío Entregado ya no cambia (estado
    final; también lo impide el trigger de la migración 013).
    """
    entregado = str(estado).strip().casefold() == "entregado"
    if entregado and fecha_entrega is None:
        raise ValueError("Pasar a Entregado requiere la fecha real de entrega.")

    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                UPDATE envio
                SET estado = %s,
                    fecha_entrega = %s
                WHERE id_envio = %s
                  AND LOWER(BTRIM(estado)) <> 'entregado'
                """,
                (estado, fecha_entrega if entregado else None, id_envio)
            )
            actualizado = cursor.rowcount > 0

            if actualizado and entregado:
                # En la misma transacción: los sensores de sus contenedores
                # dejan de transmitir; pasan a Inactivo para no generar
                # alertas falsas de "sin transmisión".
                cursor.execute(
                    """
                    UPDATE sensor_iot s
                    SET estado = 'Inactivo',
                        motivo_inactivo = 'Entrega del envío ' || %s::text
                    FROM envio_contenedor ec
                    WHERE ec.id_envio = %s
                      AND s.id_contenedor = ec.id_contenedor
                      AND s.estado = 'Activo'
                    """,
                    (id_envio, id_envio)
                )

            return actualizado


def listar_ids_envios():
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute(
                "SELECT id_envio FROM envio ORDER BY id_envio"
            )
            return [fila[0] for fila in cursor.fetchall()]


def listar_envios_de_contenedor(id_contenedor):
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT e.id_envio, e.estado, e.origen,
                       e.destino, e.fecha_creacion
                FROM envio_contenedor ec
                JOIN envio e ON e.id_envio = ec.id_envio
                WHERE ec.id_contenedor = %s
                ORDER BY e.id_envio
            """, (id_contenedor,))
            return cursor.fetchall()


def _operador(columnas):
    id_operador, razon_social, modalidades, estado = columnas
    if id_operador is None:
        return None
    return {
        "id_operador": id_operador,
        "razon_social": razon_social,
        "modalidades": list(modalidades or []),
        "estado": estado,
    }


def obtener_datos_proyeccion(id_envio):
    """Datos de PostgreSQL necesarios para proyectar un envío en Neo4j.

    Devuelve None si el envío no existe.
    """
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT e.id_envio, e.estado, e.prioridad, e.origen,
                       e.destino, e.fecha_creacion,
                       c.id_cliente, c.razon_social, c.pais
                FROM envio e
                JOIN cliente c ON c.id_cliente = e.id_cliente
                WHERE e.id_envio = %s
            """, (id_envio,))
            fila = cursor.fetchone()

            if fila is None:
                return None

            cursor.execute("""
                SELECT t.id_tramo, t.medio_transporte, t.origen,
                       t.destino, t.fecha_salida,
                       t.fecha_estimada_llegada,
                       v.id_vehiculo, v.identificacion, v.tipo,
                       ot.id_operador, ot.razon_social, ot.modalidades,
                       ot.estado,
                       ov.id_operador, ov.razon_social, ov.modalidades,
                       ov.estado
                FROM tramo t
                JOIN vehiculo v ON v.id_vehiculo = t.id_vehiculo
                LEFT JOIN operador_logistico ot
                       ON ot.id_operador = t.id_operador
                LEFT JOIN operador_logistico ov
                       ON ov.id_operador = v.id_operador
                WHERE t.id_envio = %s
                ORDER BY t.fecha_salida, t.id_tramo
            """, (id_envio,))
            tramos = cursor.fetchall()

            cursor.execute("""
                SELECT c.id_contenedor, c.codigo_internacional
                FROM envio_contenedor ec
                JOIN contenedor c ON c.id_contenedor = ec.id_contenedor
                WHERE ec.id_envio = %s
                ORDER BY c.id_contenedor
            """, (id_envio,))
            contenedores = cursor.fetchall()

    return {
        "envio": {
            "id_envio": fila[0],
            "estado": fila[1],
            "prioridad": fila[2],
            "origen": fila[3],
            "destino": fila[4],
            "fecha_creacion": fila[5].isoformat()
        },
        "cliente": {
            "id_cliente": fila[6],
            "razon_social": fila[7],
            "pais": fila[8]
        },
        "tramos": [
            {
                "id_tramo": t[0],
                "medio_transporte": t[1],
                "origen": t[2],
                "destino": t[3],
                "fecha_salida": t[4].isoformat() if t[4] else None,
                "fecha_estimada_llegada": t[5].isoformat() if t[5] else None,
                "id_vehiculo": t[6],
                "identificacion": t[7],
                "tipo_vehiculo": t[8],
                # Operador que realizó el tramo y operador actual del
                # vehículo (pueden diferir). None si no hay asignado.
                "operador": _operador(t[9:13]),
                "operador_vehiculo": _operador(t[13:17])
            }
            for t in tramos
        ],
        "contenedores": [
            {"id_contenedor": c[0], "codigo": c[1]}
            for c in contenedores
        ]
    }
