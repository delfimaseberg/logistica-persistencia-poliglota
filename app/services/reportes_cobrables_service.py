"""Reportes cobrables: solicitado -> generado -> facturado (o error).

Cada generador recibe el id_cliente y SOLO consulta datos de ese cliente.
La facturación es inmediata al generar: una factura por reporte.
"""

from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from app.repositories import reportes_repository as repo
from app.repositories.facturacion_repository import (
    FacturaExistente,
    emitir_factura_reporte,
)
from app.services.reportes_service import con_vacio, retrasos_por_envio, situacion, horas
from app.utils.exportar_reportes import CARPETA_REPORTES, Tabla, exportar
from app.utils.logger import obtener_logger
from app.utils import formato
from app.utils.errores import mensaje_error


ZONA = ZoneInfo("America/Argentina/Buenos_Aires")
FORMATOS = ("CSV", "PDF")  # formatos de archivo que se pueden pedir
MAX_DIAS = 366  # período máximo de un reporte: un año
logger = obtener_logger("reportes_cobrables")

# Parámetros extra opcionales por tipo: nombre -> (descripción, conversión).
EXTRAS = {  # filtros opcionales de cada tipo; los pide pedir_solicitud y los controla validar_parametros
    "INCIDENTES": {"severidad": ("Severidad (Baja/Media/Alta)", str),
                   "estado": ("Estado (Abierto/En proceso/Cerrado)", str)},
    "PUNTUALIDAD": {"ruta": ("Ruta (texto, ej. Mendoza)", str)},
    "OPERADORES": {"id_contenedor": ("ID de contenedor", int)},
    "CONDICIONES_CARGA": {"id_contenedor": ("ID de contenedor", int)},
    "PREDICTIVO": {},
}
# Tipos que no piden período: muestran la situación al día de la solicitud.
SIN_PERIODO = {"PREDICTIVO"}  # lo usan validar_parametros y la pantalla del pedido


def hoy():  # fecha de hoy en Argentina; la usan la validación del período y las pantallas de reportes
    return datetime.now(ZONA).date()


def validar_parametros(tipo, parametros, hoy_=None):  # controla y normaliza los filtros de un pedido; la usa solicitar_reporte
    """Normaliza {desde, hasta, extras...}. Fechas ISO; extras vacíos se omiten."""
    if tipo not in EXTRAS:
        raise ValueError("Tipo de reporte inválido.")
    hoy_ = hoy_ or hoy()
    if tipo in SIN_PERIODO:  # el predictivo solo guarda la fecha del pedido
        return {"fecha_corte": hoy_.isoformat()}
    try:
        desde = date.fromisoformat(str(parametros.get("desde")))
        hasta = date.fromisoformat(str(parametros.get("hasta")))
    except ValueError:
        raise ValueError("Las fechas deben tener el formato AAAA-MM-DD.") from None
    if desde > hasta:
        raise ValueError("La fecha 'desde' no puede ser posterior a 'hasta'.")
    if hasta > hoy_:
        raise ValueError("La fecha 'hasta' no puede ser futura.")
    if (hasta - desde).days > MAX_DIAS:  # no más de un año
        raise ValueError(f"El período no puede superar {MAX_DIAS} días.")
    normalizados = {"desde": desde.isoformat(), "hasta": hasta.isoformat()}
    for nombre, (_, convertir) in EXTRAS[tipo].items():  # convierte los filtros extra; los vacíos se omiten
        valor = parametros.get(nombre)
        if valor in (None, ""):
            continue
        try:
            normalizados[nombre] = convertir(str(valor).strip())
        except ValueError:
            raise ValueError(f"Valor inválido para {nombre}.") from None
    return normalizados


def _fecha_texto(iso):  # AAAA-MM-DD a dd/mm/aaaa; la usa describir_parametros
    return date.fromisoformat(iso).strftime("%d/%m/%Y")


def describir_parametros(params):  # los filtros del pedido en palabras; los usan el encabezado del archivo y las pantallas de reportes
    """Parámetros en lenguaje natural: ['Período: 01/05/2026 al 31/10/2026', ...]."""
    params = params or {}
    lineas = []
    if params.get("desde") and params.get("hasta"):
        lineas.append(f"Período: {_fecha_texto(params['desde'])} al {_fecha_texto(params['hasta'])}")
    if params.get("fecha_corte"):
        lineas.append(f"Situación al: {_fecha_texto(params['fecha_corte'])}")
    if params.get("id_contenedor"):  # muestra el código del contenedor en vez del ID
        from app.services.alertas_service import codigo_contenedor
        try:
            codigo = codigo_contenedor(int(params["id_contenedor"]))
        except Exception:
            codigo = None
        lineas.append(f"Contenedor: {codigo or params['id_contenedor']}")
    if params.get("severidad"):
        lineas.append(f"Severidad: {params['severidad']}")
    if params.get("estado"):
        lineas.append(f"Estado: {params['estado']}")
    if params.get("ruta"):
        lineas.append(f"Ruta: {params['ruta']}")
    return lineas


def _rango(params):  # desde y hasta como fechas; lo usan los generadores
    return date.fromisoformat(params["desde"]), date.fromisoformat(params["hasta"])


def _instantes(desde, hasta):  # el período como instantes en hora argentina, para filtrar en MongoDB y Cassandra
    """[desde 00:00, hasta+1 00:00) en hora argentina."""
    return (datetime.combine(desde, time(), ZONA),
            datetime.combine(hasta + timedelta(days=1), time(), ZONA))


# ------------------------------------------------------------ generadores

@con_vacio("No hay incidentes ni alertas de tus envíos")
def generar_incidentes(id_cliente, params):  # reporte cobrable INCIDENTES: incidentes (PostgreSQL) más alertas de sus contenedores (MongoDB)
    from app.repositories.alerta_repository import listar_alertas_contenedores
    desde, hasta = _rango(params)
    filas = [("Incidente", f[0], f[1], None, f[3], f[4], f[5], f[6])
             for f in repo.incidentes_cliente(id_cliente, desde, hasta,
                                              params.get("severidad"), params.get("estado"))]
    contenedores = {c[0]: c[1] for c in repo.contenedores_cliente(id_cliente, desde, hasta)}  # contenedores del cliente en el período, para buscar sus alertas
    inicio, fin = _instantes(desde, hasta)
    for alerta in listar_alertas_contenedores(list(contenedores), inicio, fin):  # alertas de MongoDB de esos contenedores
        if params.get("severidad") and str(alerta.get("severidad", "")).lower() != params["severidad"].lower():
            continue
        fecha = alerta.get("fecha")
        if fecha is not None and fecha.tzinfo is None:
            fecha = fecha.replace(tzinfo=timezone.utc)   # MongoDB guarda UTC
        filas.append(("Alerta IoT", fecha, alerta.get("envio_id"),
                      contenedores.get(alerta.get("contenedor_id")), alerta.get("tipo"),
                      alerta.get("severidad"), alerta.get("estado"), alerta.get("descripcion")))
    filas.sort(key=lambda f: f[1] or datetime.min.replace(tzinfo=timezone.utc))  # incidentes y alertas juntos, en orden de fecha
    return Tabla("Incidentes y alertas de mis envíos",
                 ["Origen", "Fecha", "Envío", "Contenedor", "Tipo", "Severidad", "Estado", "Descripción"],
                 filas, "PostgreSQL (incidentes) + MongoDB (alertas de sus contenedores)")


@con_vacio("No hay envíos")
def generar_puntualidad(id_cliente, params, ahora=None):  # reporte cobrable PUNTUALIDAD: si cada envío llegó a tiempo, tarde o está demorado
    desde, hasta = _rango(params)
    filas = repo.puntualidad_cliente(id_cliente, desde, hasta, params.get("ruta"))
    retrasos = retrasos_por_envio([f[0] for f in filas])  # eventos RETRASO de MongoDB
    salida = []
    for (id_envio, origen, destino, p_origen, p_destino, estado, creado,
         estimada, entrega) in filas:
        resultado = situacion(estado, estimada, entrega, ahora)  # misma regla que el reporte interno de desempeño
        diferencia = None
        if resultado in ("A tiempo", "Tarde"):
            diferencia = horas(entrega - estimada)  # negativo si llegó antes de lo estimado
        elif resultado == "Demorado":
            diferencia = horas((ahora or datetime.now(ZONA)) - estimada)
        cantidad, motivo = retrasos.get(id_envio, (0, None))
        salida.append((id_envio, f"{origen} -> {destino}",
                       f"{p_origen or 'Sin dato'} -> {p_destino or 'Sin dato'}",
                       estado, estimada, entrega, resultado, diferencia, cantidad, motivo))
    resumen = {}
    for fila in salida:
        resumen[fila[6]] = resumen.get(fila[6], 0) + 1
    return Tabla("Puntualidad de mis envíos",
                 ["Envío", "Ruta", "Países", "Estado", "Llegada estimada", "Entrega",
                  "Situación", "Horas (+ tarde / - antes)", "Retrasos informados", "Último motivo"],
                 salida, "PostgreSQL + MongoDB (eventos RETRASO)",
                 ["Resumen: " + ", ".join(f"{k}: {v}" for k, v in sorted(resumen.items()))]
                 if resumen else [])


@con_vacio("No hay tramos con operador asignado para tus contenedores")
def generar_operadores(id_cliente, params):  # reporte cobrable OPERADORES: quién llevó cada contenedor, desde el grafo de Neo4j
    from app.repositories.grafo_repository import operadores_de_contenedores_cliente
    desde, hasta = _rango(params)
    ids = repo.ids_envios_cliente(id_cliente, desde, hasta)
    filas = operadores_de_contenedores_cliente(id_cliente, ids, params.get("id_contenedor"))  # recorre el grafo filtrando por el cliente
    return Tabla("Operadores que llevaron mis contenedores",
                 ["Contenedor", "Envío", "Tramo", "Medio", "Origen", "Destino", "Salida", "Operador"],
                 [(f["contenedor"], f["id_envio"], f["id_tramo"], f["medio"], f["origen"],
                   f["destino"], formato.fecha_tramo(f["salida"]),
                   f["operador"] or "Sin asignar") for f in filas],
                 "Neo4j (grafo cliente-envío-contenedor-tramo-operador) + PostgreSQL (período)")


def limites_carga():  # rangos permitidos según las reglas de alerta activas; la usa generar_condiciones_carga
    """(temp. mínima, temp. máxima, humedad máxima) de las reglas de alerta activas."""
    from app.repositories.regla_alerta_repository import reglas_vigentes, umbral
    vigentes = reglas_vigentes()
    return (umbral(vigentes, "temperatura", "MIN", 2.0),
            umbral(vigentes, "temperatura", "MAX", 8.0),
            umbral(vigentes, "humedad", "MAX", 80.0))


@con_vacio("No hay contenedores con lecturas")
def generar_condiciones_carga(id_cliente, params):  # reporte cobrable CONDICIONES_CARGA: temperatura, humedad y GPS de las lecturas (Cassandra)
    from app.repositories.lectura_iot_repository import consultar_lecturas_contenedor_periodo
    temp_min, temp_max, hum_max = limites_carga()
    desde, hasta = _rango(params)
    inicio, fin = _instantes(desde, hasta)
    filas = []
    for id_cont, codigo, tipo, id_envio, creado, terminado in repo.contenedores_cliente(
            id_cliente, desde, hasta, params.get("id_contenedor")):
        # Solo el tramo de tiempo en que el contenedor viajó para ESTE cliente.
        lecturas = consultar_lecturas_contenedor_periodo(  # lecturas de Cassandra en ese lapso
            id_cont, max(inicio, creado), min(fin, terminado))
        temps = [l.temperatura for l in lecturas if l.temperatura is not None]
        hums = [l.humedad for l in lecturas if l.humedad is not None]
        gps = [l for l in lecturas if l.gps_latitud is not None]
        fuera = sum(1 for t in temps if not temp_min <= t <= temp_max)  # lecturas fuera del rango de temperatura o con humedad de más
        fuera += sum(1 for h in hums if h > hum_max)
        filas.append((codigo, tipo, id_envio, len(lecturas),
                      min(temps) if temps else None, max(temps) if temps else None,
                      min(hums) if hums else None, max(hums) if hums else None, fuera,
                      f"{formato.numero(gps[0].gps_latitud, 4)} ; {formato.numero(gps[0].gps_longitud, 4)}" if gps else None,
                      f"{formato.numero(gps[-1].gps_latitud, 4)} ; {formato.numero(gps[-1].gps_longitud, 4)}" if gps else None))
    return Tabla("Condiciones de la carga en viaje",
                 ["Contenedor", "Tipo", "Envío", "Lecturas", "Temp. mín.", "Temp. máx.",
                  "Hum. mín.", "Hum. máx.", "Lecturas fuera de rango",
                  "Primera posición GPS", "Última posición GPS"],
                 filas, "Cassandra (lecturas_por_contenedor) + PostgreSQL (contenedores del cliente)",
                 [f"Fuera de rango: temperatura fuera de {formato.compacto(temp_min)} a "
                  f"{formato.compacto(temp_max)} °C o humedad mayor a {formato.compacto(hum_max)} %."])


@con_vacio("No hay envíos en curso")
def generar_predictivo(id_cliente, params):  # reporte cobrable PREDICTIVO: el reporte interno de riesgo, solo con los envíos del cliente
    """Solo los envíos en curso de ESE cliente, según la última predicción."""
    from app.services.reportes_service import reporte_riesgo_envios
    tabla = reporte_riesgo_envios(id_cliente)
    columnas = [c for c in tabla.columnas if c != "Cliente"]  # saca la columna Cliente: siempre es el mismo
    tabla.filas = [tuple(v for c, v in zip(tabla.columnas, f) if c != "Cliente")
                   for f in tabla.filas]
    tabla.columnas = columnas
    tabla.titulo = "Riesgo de demora de mis envíos en curso"
    tabla.vacio = ""
    return tabla


GENERADORES = {  # qué función arma cada tipo de reporte; la usa solicitar_reporte
    "INCIDENTES": generar_incidentes,
    "PUNTUALIDAD": generar_puntualidad,
    "OPERADORES": generar_operadores,
    "CONDICIONES_CARGA": generar_condiciones_carga,
    "PREDICTIVO": generar_predictivo,
}


# ------------------------------------------------------------------ ciclo

def solicitar_reporte(id_cliente, id_usuario, tipo, formato, parametros, hoy_=None):  # pide, genera y factura un reporte; la usan Reportes > Reportes cobrables y "Mis reportes" del portal
    """Solicita, genera y factura. Devuelve el reporte final (dict).

    Si la generación falla queda ERROR y no se factura. Si la facturación
    falla queda GENERADO (se puede reintentar con facturar_pendientes).
    """
    formato = str(formato).upper()
    if formato not in FORMATOS:
        raise ValueError("Formato inválido (CSV o PDF).")
    params = validar_parametros(tipo, parametros, hoy_)
    id_reporte = repo.crear_reporte(id_cliente, id_usuario, tipo, formato, params)  # queda SOLICITADO en PostgreSQL, con el precio vigente
    logger.info("Reporte %s solicitado: cliente=%s tipo=%s", id_reporte, id_cliente, tipo)

    try:
        tabla = GENERADORES[tipo](id_cliente, params)  # arma la tabla solo con datos de ese cliente
        reporte = repo.obtener_reporte(id_reporte)
        encabezado = ([f"Reporte N.º {id_reporte} - {reporte['cliente']}"]
                      + describir_parametros(params)
                      + [f"Generado: {datetime.now(ZONA):%d/%m/%Y %H:%M}"])
        ruta, hash_ = exportar(tabla, formato,  # guarda el CSV o PDF en reportes_generados
                               Path(CARPETA_REPORTES) / f"{id_reporte}_{tipo}", encabezado)
        repo.marcar_generado(id_reporte, str(ruta), len(tabla.filas), hash_)  # pasa a GENERADO con el archivo y su hash
    except Exception as error:
        logger.exception("Error al generar el reporte %s", id_reporte)
        repo.marcar_error(id_reporte, error)  # si falló, queda en ERROR y no se factura
        return repo.obtener_reporte(id_reporte)

    try:
        emitir_factura_reporte(id_reporte)  # factura y pasa a FACTURADO; si falla, queda GENERADO para reintentar después
    except Exception:
        logger.exception("No se pudo facturar el reporte %s", id_reporte)
    return repo.obtener_reporte(id_reporte)


def facturar_pendientes():  # factura los reportes que quedaron GENERADOS; la usa "Facturar reportes generados pendientes" (facturación, opción 12)
    """Factura los reportes que quedaron GENERADOS. Devuelve (facturados, errores)."""
    facturados, errores = [], []
    for reporte in repo.listar_reportes(estado="GENERADO"):
        try:
            facturados.append(emitir_factura_reporte(reporte["id_reporte"]))
        except FacturaExistente:
            continue  # ya tenía factura: no se factura de nuevo ni cuenta como error
        except Exception as error:
            errores.append((reporte["id_reporte"], mensaje_error(error)))
    return facturados, errores


def reporte_del_cliente(id_reporte, id_cliente):  # un reporte solo si es del cliente; la usa "Ver uno de mis reportes" del portal
    """El reporte si es del cliente; si no, None (como si no existiera)."""
    reporte = repo.obtener_reporte(id_reporte)
    if reporte is None or reporte["id_cliente"] != id_cliente:  # uno ajeno se trata como si no existiera
        return None
    return reporte
