"""Consultas PostgreSQL de reportes y gestión de reportes cobrables.

Los filtros de fecha son por día argentino: [desde, hasta] inclusive.
Las consultas de reportes cobrables reciben SIEMPRE el id_cliente.
"""

import json

from app.database.postgres_connection import get_postgres_connection  # todas las consultas de reportes van a PostgreSQL
from app.utils.errores import mensaje_error  # para guardar el error del reporte ya traducido


ZONA = "America/Argentina/Buenos_Aires"  # los días se cuentan en hora argentina


def _q(sql, params=()):  # ejecuta una consulta y devuelve todas las filas; la usan casi todas las funciones de acá
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.fetchall()


def _dia(columna):  # arma el SQL que pasa una fecha con hora al día argentino; lo usan los filtros por período
    return f"({columna} AT TIME ZONE '{ZONA}')::date"


# ------------------------------------------------------- 35 operativos

def envios_por_pais(desde, hasta, id_cliente=None):  # cuenta envíos por país de destino; la usa el reporte "Envíos por país de destino"
    """Por país de destino; también los países de origen. NULL = sin dato."""
    return _q(f"""
        SELECT COALESCE(e.pais_destino, 'Sin dato') AS pais_destino,  -- los envíos sin país se agrupan como Sin dato
               COUNT(*) AS envios,  -- total de envíos del país
               COUNT(*) FILTER (WHERE lower(e.estado) = 'entregado') AS entregados,  -- cuántos están entregados
               COUNT(*) FILTER (WHERE lower(e.estado) IN ('pendiente', 'en tránsito'))  -- los que siguen en curso
                   AS en_curso,
               COUNT(*) FILTER (WHERE lower(e.estado) = 'cancelado') AS cancelados,  -- los cancelados
               string_agg(DISTINCT COALESCE(e.pais_origen, 'Sin dato'), ', ')  -- los países de origen, sin repetir
                   AS paises_origen
        FROM envio e
        WHERE {_dia('e.fecha_creacion')} BETWEEN %s AND %s  -- creados en el período elegido, por día argentino
          AND (%s::bigint IS NULL OR e.id_cliente = %s::bigint)  -- si no se elige cliente, trae todos
        GROUP BY 1  -- una fila por país de destino
        ORDER BY envios DESC, pais_destino  -- primero los países con más envíos
    """, (desde, hasta, id_cliente, id_cliente))


def envios_por_estado(desde, hasta, id_cliente=None):  # cuenta envíos por estado; la usa el reporte "Envíos por estado"
    return _q(f"""
        SELECT e.estado, COUNT(*)  -- estado y cantidad
        FROM envio e
        WHERE {_dia('e.fecha_creacion')} BETWEEN %s AND %s  -- creados en el período elegido
          AND (%s::bigint IS NULL OR e.id_cliente = %s::bigint)  -- si no se elige cliente, trae todos
        GROUP BY 1  -- una fila por estado
        ORDER BY 2 DESC, 1  -- primero el estado con más envíos
    """, (desde, hasta, id_cliente, id_cliente))


def envios_por_cliente(desde, hasta, id_cliente=None):  # envíos de cada cliente por estado; la usa el reporte "Envíos por cliente"
    return _q(f"""
        SELECT c.razon_social, c.pais, COUNT(*) AS envios,  -- cliente, su país y el total de envíos
               COUNT(*) FILTER (WHERE lower(e.estado) = 'entregado') AS entregados,  -- cuántos entregados
               COUNT(*) FILTER (WHERE lower(e.estado) IN ('pendiente', 'en tránsito'))  -- pendientes o en tránsito
                   AS en_curso,
               COUNT(*) FILTER (WHERE lower(e.estado) = 'cancelado') AS cancelados  -- cancelados
        FROM envio e
        JOIN cliente c ON c.id_cliente = e.id_cliente  -- para el nombre y el país del cliente
        WHERE {_dia('e.fecha_creacion')} BETWEEN %s AND %s  -- creados en el período elegido
          AND (%s::bigint IS NULL OR e.id_cliente = %s::bigint)  -- si no se elige cliente, trae todos
        GROUP BY c.id_cliente, c.razon_social, c.pais  -- una fila por cliente
        ORDER BY envios DESC, c.razon_social  -- primero los que tienen más envíos
    """, (desde, hasta, id_cliente, id_cliente))


def envios_demorados(id_cliente=None):  # envíos en curso con la llegada estimada vencida; la usa el reporte "Envíos demorados"
    """En curso con la llegada estimada (último tramo) ya vencida."""
    return _q("""
        SELECT e.id_envio, c.razon_social, e.origen, e.destino,
               e.pais_origen, e.pais_destino, e.estado,
               MAX(t.fecha_estimada_llegada) AS llegada_estimada,  -- la llegada estimada del último tramo
               EXTRACT(EPOCH FROM (now() - MAX(t.fecha_estimada_llegada))) / 3600  -- cuántas horas pasaron desde esa llegada
                   AS horas_demora
        FROM envio e
        JOIN cliente c ON c.id_cliente = e.id_cliente  -- para la razón social
        JOIN tramo t ON t.id_envio = e.id_envio  -- solo envíos con tramos (si no, no hay llegada estimada)
        WHERE lower(e.estado) NOT IN ('entregado', 'cancelado')  -- solo los que siguen en curso
          AND (%s::bigint IS NULL OR e.id_cliente = %s::bigint)  -- si no se elige cliente, trae todos
        GROUP BY e.id_envio, c.razon_social  -- una fila por envío
        HAVING MAX(t.fecha_estimada_llegada) < now()  -- y cuya llegada estimada ya pasó
        ORDER BY horas_demora DESC  -- primero los más demorados
    """, (id_cliente, id_cliente))


def incidentes_abiertos(id_cliente=None):  # incidentes sin cerrar; la usa el reporte "Incidentes abiertos"
    return _q("""
        SELECT i.id_incidente, e.id_envio, c.razon_social,
               e.origen || ' -> ' || e.destino AS ruta, i.tipo, i.severidad,  -- arma la ruta como texto
               i.estado, i.fecha,
               EXTRACT(EPOCH FROM (now() - i.fecha)) / 86400 AS dias_abierto  -- días que lleva abierto
        FROM incidente i
        JOIN envio e ON e.id_envio = i.id_envio  -- el envío del incidente
        JOIN cliente c ON c.id_cliente = e.id_cliente  -- y su cliente
        WHERE lower(i.estado) NOT IN ('cerrado', 'resuelto')  -- solo los que siguen abiertos
          AND (%s::bigint IS NULL OR e.id_cliente = %s::bigint)  -- si no se elige cliente, trae todos
        ORDER BY i.fecha  -- del más viejo al más nuevo
    """, (id_cliente, id_cliente))


# ------------------------------------------- 36-38 / 31 envíos entregados

def envios_entregados(desde, hasta, id_cliente=None):  # entregados en el período con su llegada estimada y medios; la usan los reportes de tiempos y de desempeño
    """Entregados en el período (por fecha real de entrega).

    Columnas: id_envio, cliente, origen, destino, país origen, país destino,
    fecha_creacion, fecha_entrega, llegada estimada (máx. de tramos),
    medios (lista).
    """
    return _q(f"""
        SELECT e.id_envio, c.razon_social, e.origen, e.destino,
               e.pais_origen, e.pais_destino, e.fecha_creacion, e.fecha_entrega,
               MAX(t.fecha_estimada_llegada) AS llegada_estimada,  -- la llegada estimada del último tramo
               array_remove(array_agg(DISTINCT t.medio_transporte), NULL) AS medios  -- medios usados, sin repetir ni vacíos
        FROM envio e
        JOIN cliente c ON c.id_cliente = e.id_cliente  -- para la razón social
        LEFT JOIN tramo t ON t.id_envio = e.id_envio  -- LEFT para no perder envíos sin tramos
        WHERE lower(e.estado) = 'entregado'  -- solo entregados
          AND {_dia('e.fecha_entrega')} BETWEEN %s AND %s  -- entregados (no creados) en el período
          AND (%s::bigint IS NULL OR e.id_cliente = %s::bigint)  -- si no se elige cliente, trae todos
        GROUP BY e.id_envio, c.razon_social  -- una fila por envío
        ORDER BY e.fecha_entrega  -- en el orden en que se entregaron
    """, (desde, hasta, id_cliente, id_cliente))


# ------------------------------------------------------- 37 incidentes

AGRUPACIONES_INCIDENTES = {  # columna por la que agrupa promedio_incidentes; así nunca se arma SQL con texto del usuario
    "pais": "COALESCE(e.pais_destino, 'Sin dato')",  # país de destino (Sin dato si falta)
    "estado": "e.estado",  # estado del envío
    "cliente": "c.razon_social",  # razón social del cliente
}


def promedio_incidentes(desde, hasta, agrupacion, id_cliente=None):  # incidentes por envío agrupados por país, estado o cliente; la usa el reporte "Promedio de incidentes"
    """Envíos creados en el período, incidentes y promedio por envío."""
    expresion = AGRUPACIONES_INCIDENTES.get(agrupacion)  # solo acepta una de las tres columnas fijas
    if expresion is None:  # cualquier otra agrupación es un error
        raise ValueError("Agrupación inválida (pais, estado o cliente).")
    return _q(f"""
        SELECT {expresion} AS grupo,  -- la columna elegida para agrupar
               COUNT(*) AS envios,  -- cantidad de envíos del grupo
               COALESCE(SUM(inc.cantidad), 0) AS incidentes,  -- total de incidentes (0 si no hay)
               ROUND(COALESCE(SUM(inc.cantidad), 0)::numeric / COUNT(*), 2)  -- incidentes por envío, con dos decimales
                   AS promedio
        FROM envio e
        JOIN cliente c ON c.id_cliente = e.id_cliente  -- para agrupar por cliente
        LEFT JOIN (SELECT id_envio, COUNT(*) AS cantidad  -- cuenta los incidentes de cada envío
                   FROM incidente GROUP BY id_envio) inc  -- una fila por envío que tuvo incidentes
               ON inc.id_envio = e.id_envio  -- LEFT para que cuenten también los envíos sin incidentes
        WHERE {_dia('e.fecha_creacion')} BETWEEN %s AND %s  -- creados en el período elegido
          AND (%s::bigint IS NULL OR e.id_cliente = %s::bigint)  -- si no se elige cliente, trae todos
        GROUP BY 1  -- una fila por grupo
        ORDER BY promedio DESC, grupo  -- primero el grupo con más incidentes por envío
    """, (desde, hasta, id_cliente, id_cliente))


# ------------------------------------------------------- 39 costos

def ventas_por_medio(desde, hasta):  # lo facturado a clientes por medio de transporte; la usa "Costos por tipo de transporte"
    """Neto facturado a clientes por medio (líneas TRAMO) y cargo base."""
    return _q("""
        SELECT COALESCE(d.medio_transporte, 'Cargo base por envío') AS medio,  -- las líneas sin medio son el cargo base
               COUNT(*) AS lineas, SUM(d.importe) AS neto  -- cantidad de líneas y total sin IVA
        FROM factura_detalle d
        JOIN factura f ON f.id_factura = d.id_factura  -- para filtrar por estado y fecha de la factura
        WHERE d.concepto IN ('TRAMO', 'BASE')  -- solo líneas de tramos y de cargo base
          AND lower(f.estado) <> 'anulada'  -- las anuladas no cuentan
          AND f.fecha_emision BETWEEN %s AND %s  -- emitidas en el período
        GROUP BY 1  -- una fila por medio
    """, (desde, hasta))


def costos_operadores_por_medio(desde, hasta):  # lo que nos facturan los operadores por medio; la usa "Costos por tipo de transporte"
    """Lo que nos facturan los operadores por los tramos, por medio."""
    return _q("""
        SELECT t.medio_transporte, COUNT(*) AS facturas, SUM(fr.total) AS total  -- medio, cantidad de facturas y total
        FROM factura_recibida fr
        JOIN tramo t ON t.id_tramo = fr.id_tramo  -- cada factura de operador es de un tramo: de ahí sale el medio
        WHERE fr.estado <> 'Anulada'  -- las anuladas no cuentan
          AND fr.fecha_emision BETWEEN %s AND %s  -- emitidas en el período
        GROUP BY 1  -- una fila por medio
    """, (desde, hasta))


# ------------------------------------------------------- 27 / 28

def ranking_rutas_incidentes(desde, hasta):  # rutas ordenadas por incidentes; la usa "Rutas con más incidentes"
    return _q(f"""
        SELECT e.origen || ' -> ' || e.destino AS ruta,  -- la ruta como texto
               COALESCE(e.pais_origen, 'Sin dato') || ' -> '  -- y los países de origen y destino
                   || COALESCE(e.pais_destino, 'Sin dato') AS paises,
               COUNT(DISTINCT e.id_envio) AS envios,  -- envíos de la ruta (DISTINCT porque el JOIN repite el envío por cada incidente)
               COUNT(i.id_incidente) AS incidentes,  -- total de incidentes
               COUNT(i.id_incidente) FILTER (  -- los que siguen abiertos
                   WHERE lower(i.estado) NOT IN ('cerrado', 'resuelto')) AS abiertos,
               COUNT(i.id_incidente) FILTER (  -- los graves (severidad alta o crítica)
                   WHERE lower(i.severidad) IN ('alta', 'crítica', 'critica')) AS graves
        FROM envio e
        LEFT JOIN incidente i ON i.id_envio = e.id_envio  -- LEFT para contar los envíos aunque no tengan incidentes
        WHERE {_dia('e.fecha_creacion')} BETWEEN %s AND %s  -- creados en el período elegido
        GROUP BY 1, 2  -- una fila por ruta
        HAVING COUNT(i.id_incidente) > 0  -- solo rutas que tuvieron algún incidente
        ORDER BY incidentes DESC, graves DESC, ruta  -- primero las que tienen más incidentes
    """, (desde, hasta))


def ranking_clientes_volumen(desde, hasta):  # clientes ordenados por volumen transportado; la usa "Clientes por volumen transportado"
    """Volumen real: contenedores, capacidad (toneladas) y peso declarado (kg)."""
    return _q(f"""
        WITH envios AS (  -- envíos del período que no están cancelados
            SELECT e.id_envio, e.id_cliente
            FROM envio e
            WHERE {_dia('e.fecha_creacion')} BETWEEN %s AND %s  -- creados en el período elegido
              AND lower(e.estado) <> 'cancelado'  -- los cancelados no suman volumen
        ),
        cont AS (  -- contenedores y capacidad total por cliente
            SELECT en.id_cliente, COUNT(*) AS contenedores,
                   SUM(k.capacidad) AS capacidad  -- capacidad en toneladas
            FROM envios en
            JOIN envio_contenedor ec ON ec.id_envio = en.id_envio  -- contenedores asociados a cada envío
            JOIN contenedor k ON k.id_contenedor = ec.id_contenedor  -- para la capacidad del contenedor
            GROUP BY en.id_cliente
        ),
        peso AS (  -- peso declarado por cliente
            SELECT en.id_cliente, SUM(ca.peso_kg) AS peso_kg  -- suma el peso de las partidas de carga
            FROM envios en
            JOIN envio_carga ca ON ca.id_envio = en.id_envio  -- partidas de carga de cada envío
            GROUP BY en.id_cliente
        )
        SELECT c.razon_social, c.pais,  -- cliente y país
               (SELECT COUNT(*) FROM envios x WHERE x.id_cliente = c.id_cliente) AS envios,  -- cuántos envíos tuvo en el período
               COALESCE(cont.contenedores, 0), COALESCE(cont.capacidad, 0),  -- 0 si no tuvo contenedores
               COALESCE(peso.peso_kg, 0)  -- 0 si no declaró peso
        FROM cliente c
        LEFT JOIN cont ON cont.id_cliente = c.id_cliente  -- LEFT para no perder clientes sin contenedores
        LEFT JOIN peso ON peso.id_cliente = c.id_cliente  -- ni clientes sin partidas de carga
        WHERE EXISTS (SELECT 1 FROM envios x WHERE x.id_cliente = c.id_cliente)  -- solo clientes con envíos en el período
        ORDER BY 6 DESC, 5 DESC, c.razon_social  -- primero por peso y, a igual peso, por capacidad
    """, (desde, hasta))


# ------------------------------------------ reportes cobrables (por cliente)

def incidentes_cliente(id_cliente, desde, hasta, severidad=None, estado=None):  # incidentes de los envíos de un cliente; la usa el reporte cobrable de incidentes
    return _q(f"""
        SELECT i.fecha, e.id_envio, e.origen || ' -> ' || e.destino AS ruta,  -- la ruta como texto
               i.tipo, i.severidad, i.estado, i.descripcion
        FROM incidente i
        JOIN envio e ON e.id_envio = i.id_envio  -- el envío de cada incidente
        WHERE e.id_cliente = %s  -- siempre de un solo cliente
          AND {_dia('i.fecha')} BETWEEN %s AND %s  -- incidentes del período
          AND (%s::text IS NULL OR lower(i.severidad) = lower(%s::text))  -- filtro opcional por severidad
          AND (%s::text IS NULL OR lower(i.estado) = lower(%s::text))  -- filtro opcional por estado
        ORDER BY i.fecha  -- en orden cronológico
    """, (id_cliente, desde, hasta, severidad, severidad, estado, estado))


def contenedores_cliente(id_cliente, desde, hasta, id_contenedor=None):  # contenedores del cliente en viaje durante el período; la usan los cobrables de incidentes y de condiciones de la carga
    """Contenedores de los envíos del cliente activos en el período.

    Columnas: id_contenedor, código, tipo, id_envio, desde (creación),
    hasta (entrega o ahora).
    """
    return _q(f"""
        SELECT k.id_contenedor, k.codigo_internacional, k.tipo, e.id_envio,  -- datos del contenedor y de su envío
               e.fecha_creacion, COALESCE(e.fecha_entrega, now())  -- desde cuándo y hasta cuándo viajó (si no se entregó, hasta ahora)
        FROM envio e
        JOIN envio_contenedor ec ON ec.id_envio = e.id_envio  -- contenedores de cada envío
        JOIN contenedor k ON k.id_contenedor = ec.id_contenedor  -- para el código y el tipo
        WHERE e.id_cliente = %s  -- solo los envíos del cliente
          AND {_dia('e.fecha_creacion')} <= %s  -- que empezaron antes del fin del período
          AND {_dia('COALESCE(e.fecha_entrega, now())')} >= %s  -- y terminaron, o siguen, después del inicio
          AND (%s::bigint IS NULL OR k.id_contenedor = %s::bigint)  -- filtro opcional por contenedor
        ORDER BY k.id_contenedor, e.id_envio  -- agrupados por contenedor
    """, (id_cliente, hasta, desde, id_contenedor, id_contenedor))


def puntualidad_cliente(id_cliente, desde, hasta, ruta=None):  # envíos del cliente para ver si llegaron a tiempo; la usa el reporte cobrable de puntualidad
    """Envíos del cliente creados en el período.

    Columnas: id_envio, origen, destino, país origen, país destino, estado,
    fecha_creacion, llegada estimada (máx.), fecha_entrega.
    """
    return _q(f"""
        SELECT e.id_envio, e.origen, e.destino, e.pais_origen, e.pais_destino,
               e.estado, e.fecha_creacion, MAX(t.fecha_estimada_llegada),  -- la llegada estimada del último tramo
               e.fecha_entrega
        FROM envio e
        LEFT JOIN tramo t ON t.id_envio = e.id_envio  -- LEFT para incluir envíos sin tramos
        WHERE e.id_cliente = %s  -- solo los envíos del cliente
          AND {_dia('e.fecha_creacion')} BETWEEN %s AND %s  -- creados en el período elegido
          AND (%s::text IS NULL  -- filtro opcional por ruta
               OR lower(e.origen || ' -> ' || e.destino) LIKE '%%' || lower(%s::text) || '%%')  -- la ruta contiene el texto buscado, sin importar mayúsculas
        GROUP BY e.id_envio  -- una fila por envío
        ORDER BY e.fecha_creacion  -- en el orden en que se crearon
    """, (id_cliente, desde, hasta, ruta, ruta))


def ids_envios_cliente(id_cliente, desde, hasta):  # IDs de los envíos del cliente creados en el período; la usa el reporte cobrable de operadores
    return [fila[0] for fila in _q(f"""
        SELECT id_envio FROM envio
        WHERE id_cliente = %s AND {_dia('fecha_creacion')} BETWEEN %s AND %s  -- del cliente y creados en el período
    """, (id_cliente, desde, hasta))]


# ------------------------------------------------- gestión de reportes

def listar_tipos_reporte(solo_activos=True):  # tipos de reporte cobrable con su precio; la usan el pedido de reportes y "Precios de reportes cobrables"
    return _q("""
        SELECT codigo, nombre, descripcion, base_datos, precio, activo
        FROM tipo_reporte
        WHERE (%s = FALSE OR activo)  -- con solo_activos, solo los activos; si no, todos
        ORDER BY codigo
    """, (solo_activos,))


def actualizar_precio_tipo_reporte(codigo, precio, id_usuario):  # cambia el precio de un tipo; la usa "Precios de reportes cobrables"
    from app.utils.validaciones_datos import validar_importe
    precio = validar_importe(precio, "El precio")  # mayor a cero, dos decimales y hasta el máximo por operación
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                UPDATE tipo_reporte
                SET precio = %s, actualizado_por = %s,  -- precio nuevo y quién lo cambió
                    actualizado_en = CURRENT_TIMESTAMP  -- y cuándo
                WHERE codigo = %s  -- del tipo elegido
            """, (precio, id_usuario, codigo))
            return cursor.rowcount == 1  # True si el tipo existía


def crear_reporte(id_cliente, id_usuario, tipo, formato, parametros):  # registra el pedido de un reporte cobrable; la usa solicitar_reporte
    """Registra la solicitud con el precio vigente del tipo (SOLICITADO)."""
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT precio FROM tipo_reporte  -- precio vigente del tipo
                WHERE codigo = %s AND activo  -- solo si el tipo está activo
            """, (tipo,))
            fila = cursor.fetchone()
            if fila is None:  # tipo inexistente o inactivo
                raise ValueError("Tipo de reporte inexistente o inactivo.")
            cursor.execute("""
                INSERT INTO reporte (  -- guarda el pedido
                    id_usuario, id_cliente, tipo, formato, estado,
                    parametros, importe_base
                )
                VALUES (%s, %s, %s, %s, 'SOLICITADO', %s::jsonb, %s)  -- arranca como SOLICITADO; los filtros van como JSON
                RETURNING id_reporte  -- devuelve el número de reporte
            """, (id_usuario, id_cliente, tipo, formato,
                  json.dumps(parametros, ensure_ascii=False), fila[0]))  # filtros en JSON y el precio vigente
            return cursor.fetchone()[0]


def marcar_generado(id_reporte, archivo, filas, hash_archivo):  # deja el reporte en GENERADO con su archivo y hash; la usa la generación del reporte cobrable
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                UPDATE reporte
                SET estado = 'GENERADO', archivo = %s, filas = %s,  -- ruta del archivo y cuántas filas tuvo
                    hash_archivo = %s, fecha_generacion = CURRENT_TIMESTAMP,  -- hash para comprobar que el archivo no cambió
                    error = NULL  -- limpia un error anterior
                WHERE id_reporte = %s AND estado = 'SOLICITADO'  -- solo si todavía estaba pedido
            """, (archivo, filas, hash_archivo, id_reporte))
            if cursor.rowcount != 1:  # si ya no estaba SOLICITADO, no se pisa
                raise ValueError("El reporte no está en estado SOLICITADO.")


def marcar_error(id_reporte, error):  # deja el reporte en ERROR con el motivo; la usa la generación cuando algo falla
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                UPDATE reporte SET estado = 'ERROR', error = %s  -- guarda el motivo ya traducido
                WHERE id_reporte = %s AND estado = 'SOLICITADO'  -- solo si seguía pedido
            """, (mensaje_error(error)[:2000], id_reporte))


COLUMNAS_REPORTE = (  # nombres de las columnas de _select_reportes, para armar los diccionarios
    "id_reporte", "id_cliente", "cliente", "id_usuario", "usuario", "tipo",
    "formato", "estado", "parametros", "importe_base", "fecha_solicitud",
    "fecha_generacion", "archivo", "filas", "hash_archivo", "error", "id_factura",
    "total_factura",
)


def _select_reportes(condicion):  # arma el SELECT de reportes con cliente, usuario y factura; lo usan obtener_reporte y listar_reportes
    return f"""
        SELECT r.id_reporte, r.id_cliente, c.razon_social, r.id_usuario,  -- datos del reporte y del cliente
               u.nombre || ' ' || u.apellido, r.tipo, r.formato, r.estado,  -- nombre completo de quien lo pidió
               r.parametros, r.importe_base, r.fecha_solicitud,
               r.fecha_generacion, r.archivo, r.filas, r.hash_archivo, r.error,
               f.id_factura, f.total  -- la factura, si ya se facturó
        FROM reporte r
        JOIN cliente c ON c.id_cliente = r.id_cliente  -- razón social del cliente
        JOIN usuario u ON u.id_usuario = r.id_usuario  -- quién lo pidió
        LEFT JOIN factura f ON f.id_reporte = r.id_reporte  -- LEFT porque puede no estar facturado todavía
        {condicion}
        ORDER BY r.fecha_solicitud DESC, r.id_reporte DESC  -- los más nuevos primero
    """


def obtener_reporte(id_reporte):  # un reporte por número; la usan "Ver un reporte" y los reportes cobrables
    filas = _q(_select_reportes("WHERE r.id_reporte = %s"), (id_reporte,))  # filtra por número de reporte
    return dict(zip(COLUMNAS_REPORTE, filas[0])) if filas else None  # diccionario con nombres de columna, o None


def listar_reportes(id_cliente=None, estado=None):  # reportes cobrables con filtros opcionales; la usan "Listar reportes", "Mis reportes" y la facturación de pendientes
    filas = _q(_select_reportes(
        "WHERE (%s::bigint IS NULL OR r.id_cliente = %s::bigint) "  # cliente opcional
        "AND (%s::text IS NULL OR r.estado = %s::text)"  # estado opcional (por ejemplo, GENERADO)
    ), (id_cliente, id_cliente, estado, estado))
    return [dict(zip(COLUMNAS_REPORTE, fila)) for fila in filas]


# ------------------------------------------------------- 34 predictivos

def envios_en_curso(id_cliente=None):  # envíos no entregados ni cancelados; la usan los reportes predictivos
    """Envíos no entregados ni cancelados (opcionalmente de un cliente)."""
    return _q("""
        SELECT e.id_envio, c.razon_social, e.origen, e.destino, e.estado  -- datos básicos del envío y su cliente
        FROM envio e
        JOIN cliente c ON c.id_cliente = e.id_cliente  -- para la razón social
        WHERE lower(e.estado) NOT IN ('entregado', 'cancelado')  -- solo los que siguen en curso
          AND (%s::bigint IS NULL OR e.id_cliente = %s::bigint)  -- si no se elige cliente, trae todos
        ORDER BY e.id_envio
    """, (id_cliente, id_cliente))
