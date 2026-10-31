"""Consultas PostgreSQL de reportes y gestión de reportes cobrables.

Los filtros de fecha son por día argentino: [desde, hasta] inclusive.
Las consultas de reportes cobrables reciben SIEMPRE el id_cliente.
"""

import json

from app.database.postgres_connection import get_postgres_connection


ZONA = "America/Argentina/Buenos_Aires"


def _q(sql, params=()):
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.fetchall()


def _dia(columna):
    return f"({columna} AT TIME ZONE '{ZONA}')::date"


# ------------------------------------------------------- 35 operativos

def envios_por_pais(desde, hasta, id_cliente=None):
    """Por país de destino; también los países de origen. NULL = sin dato."""
    return _q(f"""
        SELECT COALESCE(e.pais_destino, 'Sin dato') AS pais_destino,
               COUNT(*) AS envios,
               COUNT(*) FILTER (WHERE lower(e.estado) = 'entregado') AS entregados,
               COUNT(*) FILTER (WHERE lower(e.estado) IN ('pendiente', 'en tránsito'))
                   AS en_curso,
               COUNT(*) FILTER (WHERE lower(e.estado) = 'cancelado') AS cancelados,
               string_agg(DISTINCT COALESCE(e.pais_origen, 'Sin dato'), ', ')
                   AS paises_origen
        FROM envio e
        WHERE {_dia('e.fecha_creacion')} BETWEEN %s AND %s
          AND (%s::bigint IS NULL OR e.id_cliente = %s::bigint)
        GROUP BY 1
        ORDER BY envios DESC, pais_destino
    """, (desde, hasta, id_cliente, id_cliente))


def envios_por_estado(desde, hasta, id_cliente=None):
    return _q(f"""
        SELECT e.estado, COUNT(*)
        FROM envio e
        WHERE {_dia('e.fecha_creacion')} BETWEEN %s AND %s
          AND (%s::bigint IS NULL OR e.id_cliente = %s::bigint)
        GROUP BY 1
        ORDER BY 2 DESC, 1
    """, (desde, hasta, id_cliente, id_cliente))


def envios_por_cliente(desde, hasta, id_cliente=None):
    return _q(f"""
        SELECT c.razon_social, c.pais, COUNT(*) AS envios,
               COUNT(*) FILTER (WHERE lower(e.estado) = 'entregado') AS entregados,
               COUNT(*) FILTER (WHERE lower(e.estado) IN ('pendiente', 'en tránsito'))
                   AS en_curso,
               COUNT(*) FILTER (WHERE lower(e.estado) = 'cancelado') AS cancelados
        FROM envio e
        JOIN cliente c ON c.id_cliente = e.id_cliente
        WHERE {_dia('e.fecha_creacion')} BETWEEN %s AND %s
          AND (%s::bigint IS NULL OR e.id_cliente = %s::bigint)
        GROUP BY c.id_cliente, c.razon_social, c.pais
        ORDER BY envios DESC, c.razon_social
    """, (desde, hasta, id_cliente, id_cliente))


def envios_demorados(id_cliente=None):
    """En curso con la llegada estimada (último tramo) ya vencida."""
    return _q("""
        SELECT e.id_envio, c.razon_social, e.origen, e.destino,
               e.pais_origen, e.pais_destino, e.estado,
               MAX(t.fecha_estimada_llegada) AS llegada_estimada,
               EXTRACT(EPOCH FROM (now() - MAX(t.fecha_estimada_llegada))) / 3600
                   AS horas_demora
        FROM envio e
        JOIN cliente c ON c.id_cliente = e.id_cliente
        JOIN tramo t ON t.id_envio = e.id_envio
        WHERE lower(e.estado) NOT IN ('entregado', 'cancelado')
          AND (%s::bigint IS NULL OR e.id_cliente = %s::bigint)
        GROUP BY e.id_envio, c.razon_social
        HAVING MAX(t.fecha_estimada_llegada) < now()
        ORDER BY horas_demora DESC
    """, (id_cliente, id_cliente))


def incidentes_abiertos(id_cliente=None):
    return _q("""
        SELECT i.id_incidente, e.id_envio, c.razon_social,
               e.origen || ' -> ' || e.destino AS ruta, i.tipo, i.severidad,
               i.estado, i.fecha,
               EXTRACT(EPOCH FROM (now() - i.fecha)) / 86400 AS dias_abierto
        FROM incidente i
        JOIN envio e ON e.id_envio = i.id_envio
        JOIN cliente c ON c.id_cliente = e.id_cliente
        WHERE lower(i.estado) NOT IN ('cerrado', 'resuelto')
          AND (%s::bigint IS NULL OR e.id_cliente = %s::bigint)
        ORDER BY i.fecha
    """, (id_cliente, id_cliente))


# ------------------------------------------- 36-38 / 31 envíos entregados

def envios_entregados(desde, hasta, id_cliente=None):
    """Entregados en el período (por fecha real de entrega).

    Columnas: id_envio, cliente, origen, destino, país origen, país destino,
    fecha_creacion, fecha_entrega, llegada estimada (máx. de tramos),
    medios (lista).
    """
    return _q(f"""
        SELECT e.id_envio, c.razon_social, e.origen, e.destino,
               e.pais_origen, e.pais_destino, e.fecha_creacion, e.fecha_entrega,
               MAX(t.fecha_estimada_llegada) AS llegada_estimada,
               array_remove(array_agg(DISTINCT t.medio_transporte), NULL) AS medios
        FROM envio e
        JOIN cliente c ON c.id_cliente = e.id_cliente
        LEFT JOIN tramo t ON t.id_envio = e.id_envio
        WHERE lower(e.estado) = 'entregado'
          AND {_dia('e.fecha_entrega')} BETWEEN %s AND %s
          AND (%s::bigint IS NULL OR e.id_cliente = %s::bigint)
        GROUP BY e.id_envio, c.razon_social
        ORDER BY e.fecha_entrega
    """, (desde, hasta, id_cliente, id_cliente))


# ------------------------------------------------------- 37 incidentes

AGRUPACIONES_INCIDENTES = {
    "pais": "COALESCE(e.pais_destino, 'Sin dato')",
    "estado": "e.estado",
    "cliente": "c.razon_social",
}


def promedio_incidentes(desde, hasta, agrupacion, id_cliente=None):
    """Envíos creados en el período, incidentes y promedio por envío."""
    expresion = AGRUPACIONES_INCIDENTES.get(agrupacion)
    if expresion is None:
        raise ValueError("Agrupación inválida (pais, estado o cliente).")
    return _q(f"""
        SELECT {expresion} AS grupo,
               COUNT(*) AS envios,
               COALESCE(SUM(inc.cantidad), 0) AS incidentes,
               ROUND(COALESCE(SUM(inc.cantidad), 0)::numeric / COUNT(*), 2)
                   AS promedio
        FROM envio e
        JOIN cliente c ON c.id_cliente = e.id_cliente
        LEFT JOIN (SELECT id_envio, COUNT(*) AS cantidad
                   FROM incidente GROUP BY id_envio) inc
               ON inc.id_envio = e.id_envio
        WHERE {_dia('e.fecha_creacion')} BETWEEN %s AND %s
          AND (%s::bigint IS NULL OR e.id_cliente = %s::bigint)
        GROUP BY 1
        ORDER BY promedio DESC, grupo
    """, (desde, hasta, id_cliente, id_cliente))


# ------------------------------------------------------- 39 costos

def ventas_por_medio(desde, hasta):
    """Neto facturado a clientes por medio (líneas TRAMO) y cargo base."""
    return _q("""
        SELECT COALESCE(d.medio_transporte, 'Cargo base por envío') AS medio,
               COUNT(*) AS lineas, SUM(d.importe) AS neto
        FROM factura_detalle d
        JOIN factura f ON f.id_factura = d.id_factura
        WHERE d.concepto IN ('TRAMO', 'BASE')
          AND lower(f.estado) <> 'anulada'
          AND f.fecha_emision BETWEEN %s AND %s
        GROUP BY 1
    """, (desde, hasta))


def costos_operadores_por_medio(desde, hasta):
    """Lo que nos facturan los operadores por los tramos, por medio."""
    return _q("""
        SELECT t.medio_transporte, COUNT(*) AS facturas, SUM(fr.total) AS total
        FROM factura_recibida fr
        JOIN tramo t ON t.id_tramo = fr.id_tramo
        WHERE fr.estado <> 'Anulada'
          AND fr.fecha_emision BETWEEN %s AND %s
        GROUP BY 1
    """, (desde, hasta))


# ------------------------------------------------------- 27 / 28

def ranking_rutas_incidentes(desde, hasta):
    return _q(f"""
        SELECT e.origen || ' -> ' || e.destino AS ruta,
               COALESCE(e.pais_origen, 'Sin dato') || ' -> '
                   || COALESCE(e.pais_destino, 'Sin dato') AS paises,
               COUNT(DISTINCT e.id_envio) AS envios,
               COUNT(i.id_incidente) AS incidentes,
               COUNT(i.id_incidente) FILTER (
                   WHERE lower(i.estado) NOT IN ('cerrado', 'resuelto')) AS abiertos,
               COUNT(i.id_incidente) FILTER (
                   WHERE lower(i.severidad) IN ('alta', 'crítica', 'critica')) AS graves
        FROM envio e
        LEFT JOIN incidente i ON i.id_envio = e.id_envio
        WHERE {_dia('e.fecha_creacion')} BETWEEN %s AND %s
        GROUP BY 1, 2
        HAVING COUNT(i.id_incidente) > 0
        ORDER BY incidentes DESC, graves DESC, ruta
    """, (desde, hasta))


def ranking_clientes_volumen(desde, hasta):
    """Volumen real: contenedores, capacidad (m3) y peso declarado (kg)."""
    return _q(f"""
        WITH envios AS (
            SELECT e.id_envio, e.id_cliente
            FROM envio e
            WHERE {_dia('e.fecha_creacion')} BETWEEN %s AND %s
              AND lower(e.estado) <> 'cancelado'
        ),
        cont AS (
            SELECT en.id_cliente, COUNT(*) AS contenedores,
                   SUM(k.capacidad) AS capacidad
            FROM envios en
            JOIN envio_contenedor ec ON ec.id_envio = en.id_envio
            JOIN contenedor k ON k.id_contenedor = ec.id_contenedor
            GROUP BY en.id_cliente
        ),
        peso AS (
            SELECT en.id_cliente, SUM(ca.peso_kg) AS peso_kg
            FROM envios en
            JOIN envio_carga ca ON ca.id_envio = en.id_envio
            GROUP BY en.id_cliente
        )
        SELECT c.razon_social, c.pais,
               (SELECT COUNT(*) FROM envios x WHERE x.id_cliente = c.id_cliente) AS envios,
               COALESCE(cont.contenedores, 0), COALESCE(cont.capacidad, 0),
               COALESCE(peso.peso_kg, 0)
        FROM cliente c
        LEFT JOIN cont ON cont.id_cliente = c.id_cliente
        LEFT JOIN peso ON peso.id_cliente = c.id_cliente
        WHERE EXISTS (SELECT 1 FROM envios x WHERE x.id_cliente = c.id_cliente)
        ORDER BY 6 DESC, 5 DESC, c.razon_social
    """, (desde, hasta))


# ------------------------------------------ reportes cobrables (por cliente)

def incidentes_cliente(id_cliente, desde, hasta, severidad=None, estado=None):
    return _q(f"""
        SELECT i.fecha, e.id_envio, e.origen || ' -> ' || e.destino AS ruta,
               i.tipo, i.severidad, i.estado, i.descripcion
        FROM incidente i
        JOIN envio e ON e.id_envio = i.id_envio
        WHERE e.id_cliente = %s
          AND {_dia('i.fecha')} BETWEEN %s AND %s
          AND (%s::text IS NULL OR lower(i.severidad) = lower(%s::text))
          AND (%s::text IS NULL OR lower(i.estado) = lower(%s::text))
        ORDER BY i.fecha
    """, (id_cliente, desde, hasta, severidad, severidad, estado, estado))


def contenedores_cliente(id_cliente, desde, hasta, id_contenedor=None):
    """Contenedores de los envíos del cliente activos en el período.

    Columnas: id_contenedor, código, tipo, id_envio, desde (creación),
    hasta (entrega o ahora).
    """
    return _q(f"""
        SELECT k.id_contenedor, k.codigo_internacional, k.tipo, e.id_envio,
               e.fecha_creacion, COALESCE(e.fecha_entrega, now())
        FROM envio e
        JOIN envio_contenedor ec ON ec.id_envio = e.id_envio
        JOIN contenedor k ON k.id_contenedor = ec.id_contenedor
        WHERE e.id_cliente = %s
          AND {_dia('e.fecha_creacion')} <= %s
          AND {_dia('COALESCE(e.fecha_entrega, now())')} >= %s
          AND (%s::bigint IS NULL OR k.id_contenedor = %s::bigint)
        ORDER BY k.id_contenedor, e.id_envio
    """, (id_cliente, hasta, desde, id_contenedor, id_contenedor))


def puntualidad_cliente(id_cliente, desde, hasta, ruta=None):
    """Envíos del cliente creados en el período.

    Columnas: id_envio, origen, destino, país origen, país destino, estado,
    fecha_creacion, llegada estimada (máx.), fecha_entrega.
    """
    return _q(f"""
        SELECT e.id_envio, e.origen, e.destino, e.pais_origen, e.pais_destino,
               e.estado, e.fecha_creacion, MAX(t.fecha_estimada_llegada),
               e.fecha_entrega
        FROM envio e
        LEFT JOIN tramo t ON t.id_envio = e.id_envio
        WHERE e.id_cliente = %s
          AND {_dia('e.fecha_creacion')} BETWEEN %s AND %s
          AND (%s::text IS NULL
               OR lower(e.origen || ' -> ' || e.destino) LIKE '%%' || lower(%s::text) || '%%')
        GROUP BY e.id_envio
        ORDER BY e.fecha_creacion
    """, (id_cliente, desde, hasta, ruta, ruta))


def ids_envios_cliente(id_cliente, desde, hasta):
    return [fila[0] for fila in _q(f"""
        SELECT id_envio FROM envio
        WHERE id_cliente = %s AND {_dia('fecha_creacion')} BETWEEN %s AND %s
    """, (id_cliente, desde, hasta))]


# ------------------------------------------------- gestión de reportes

def listar_tipos_reporte(solo_activos=True):
    return _q("""
        SELECT codigo, nombre, descripcion, base_datos, precio, activo
        FROM tipo_reporte
        WHERE (%s = FALSE OR activo)
        ORDER BY codigo
    """, (solo_activos,))


def actualizar_precio_tipo_reporte(codigo, precio, id_usuario):
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                UPDATE tipo_reporte
                SET precio = %s, actualizado_por = %s,
                    actualizado_en = CURRENT_TIMESTAMP
                WHERE codigo = %s
            """, (precio, id_usuario, codigo))
            return cursor.rowcount == 1


def crear_reporte(id_cliente, id_usuario, tipo, formato, parametros):
    """Registra la solicitud con el precio vigente del tipo (SOLICITADO)."""
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT precio FROM tipo_reporte
                WHERE codigo = %s AND activo
            """, (tipo,))
            fila = cursor.fetchone()
            if fila is None:
                raise ValueError("Tipo de reporte inexistente o inactivo.")
            cursor.execute("""
                INSERT INTO reporte (
                    id_usuario, id_cliente, tipo, formato, estado,
                    parametros, importe_base
                )
                VALUES (%s, %s, %s, %s, 'SOLICITADO', %s::jsonb, %s)
                RETURNING id_reporte
            """, (id_usuario, id_cliente, tipo, formato,
                  json.dumps(parametros, ensure_ascii=False), fila[0]))
            return cursor.fetchone()[0]


def marcar_generado(id_reporte, archivo, filas, hash_archivo):
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                UPDATE reporte
                SET estado = 'GENERADO', archivo = %s, filas = %s,
                    hash_archivo = %s, fecha_generacion = CURRENT_TIMESTAMP,
                    error = NULL
                WHERE id_reporte = %s AND estado = 'SOLICITADO'
            """, (archivo, filas, hash_archivo, id_reporte))
            if cursor.rowcount != 1:
                raise ValueError("El reporte no está en estado SOLICITADO.")


def marcar_error(id_reporte, error):
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                UPDATE reporte SET estado = 'ERROR', error = %s
                WHERE id_reporte = %s AND estado = 'SOLICITADO'
            """, (str(error)[:2000], id_reporte))


COLUMNAS_REPORTE = (
    "id_reporte", "id_cliente", "cliente", "id_usuario", "usuario", "tipo",
    "formato", "estado", "parametros", "importe_base", "fecha_solicitud",
    "fecha_generacion", "archivo", "filas", "hash_archivo", "error", "id_factura",
    "total_factura",
)


def _select_reportes(condicion):
    return f"""
        SELECT r.id_reporte, r.id_cliente, c.razon_social, r.id_usuario,
               u.nombre || ' ' || u.apellido, r.tipo, r.formato, r.estado,
               r.parametros, r.importe_base, r.fecha_solicitud,
               r.fecha_generacion, r.archivo, r.filas, r.hash_archivo, r.error,
               f.id_factura, f.total
        FROM reporte r
        JOIN cliente c ON c.id_cliente = r.id_cliente
        JOIN usuario u ON u.id_usuario = r.id_usuario
        LEFT JOIN factura f ON f.id_reporte = r.id_reporte
        {condicion}
        ORDER BY r.fecha_solicitud DESC, r.id_reporte DESC
    """


def obtener_reporte(id_reporte):
    filas = _q(_select_reportes("WHERE r.id_reporte = %s"), (id_reporte,))
    return dict(zip(COLUMNAS_REPORTE, filas[0])) if filas else None


def listar_reportes(id_cliente=None, estado=None):
    filas = _q(_select_reportes(
        "WHERE (%s::bigint IS NULL OR r.id_cliente = %s::bigint) "
        "AND (%s::text IS NULL OR r.estado = %s::text)"
    ), (id_cliente, id_cliente, estado, estado))
    return [dict(zip(COLUMNAS_REPORTE, fila)) for fila in filas]


# ------------------------------------------------------- 34 predictivos

def envios_en_curso(id_cliente=None):
    """Envíos no entregados ni cancelados (opcionalmente de un cliente)."""
    return _q("""
        SELECT e.id_envio, c.razon_social, e.origen, e.destino, e.estado
        FROM envio e
        JOIN cliente c ON c.id_cliente = e.id_cliente
        WHERE lower(e.estado) NOT IN ('entregado', 'cancelado')
          AND (%s::bigint IS NULL OR e.id_cliente = %s::bigint)
        ORDER BY e.id_envio
    """, (id_cliente, id_cliente))
