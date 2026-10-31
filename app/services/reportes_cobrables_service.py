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


ZONA = ZoneInfo("America/Argentina/Buenos_Aires")
FORMATOS = ("CSV", "PDF")
MAX_DIAS = 366
logger = obtener_logger("reportes_cobrables")

# Parámetros extra opcionales por tipo: nombre -> (descripción, conversión).
EXTRAS = {
    "INCIDENTES": {"severidad": ("Severidad (Baja/Media/Alta)", str),
                   "estado": ("Estado (Abierto/En proceso/Cerrado)", str)},
    "PUNTUALIDAD": {"ruta": ("Ruta (texto, ej. Mendoza)", str)},
    "OPERADORES": {"id_contenedor": ("ID de contenedor", int)},
    "CONDICIONES_CARGA": {"id_contenedor": ("ID de contenedor", int)},
    "PREDICTIVO": {},
}
# Tipos que no piden período: muestran la situación al día de la solicitud.
SIN_PERIODO = {"PREDICTIVO"}


def hoy():
    return datetime.now(ZONA).date()


def validar_parametros(tipo, parametros, hoy_=None):
    """Normaliza {desde, hasta, extras...}. Fechas ISO; extras vacíos se omiten."""
    if tipo not in EXTRAS:
        raise ValueError("Tipo de reporte inválido.")
    hoy_ = hoy_ or hoy()
    if tipo in SIN_PERIODO:
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
    if (hasta - desde).days > MAX_DIAS:
        raise ValueError(f"El período no puede superar {MAX_DIAS} días.")
    normalizados = {"desde": desde.isoformat(), "hasta": hasta.isoformat()}
    for nombre, (_, convertir) in EXTRAS[tipo].items():
        valor = parametros.get(nombre)
        if valor in (None, ""):
            continue
        try:
            normalizados[nombre] = convertir(str(valor).strip())
        except ValueError:
            raise ValueError(f"Valor inválido para {nombre}.") from None
    return normalizados


def _fecha_texto(iso):
    return date.fromisoformat(iso).strftime("%d/%m/%Y")


def describir_parametros(params):
    """Parámetros en lenguaje natural: ['Período: 01/05/2026 al 31/10/2026', ...]."""
    params = params or {}
    lineas = []
    if params.get("desde") and params.get("hasta"):
        lineas.append(f"Período: {_fecha_texto(params['desde'])} al {_fecha_texto(params['hasta'])}")
    if params.get("fecha_corte"):
        lineas.append(f"Situación al: {_fecha_texto(params['fecha_corte'])}")
    if params.get("id_contenedor"):
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


def _rango(params):
    return date.fromisoformat(params["desde"]), date.fromisoformat(params["hasta"])


def _instantes(desde, hasta):
    """[desde 00:00, hasta+1 00:00) en hora argentina."""
    return (datetime.combine(desde, time(), ZONA),
            datetime.combine(hasta + timedelta(days=1), time(), ZONA))


# ------------------------------------------------------------ generadores

@con_vacio("No hay incidentes ni alertas de sus envíos")
def generar_incidentes(id_cliente, params):
    from app.repositories.alerta_repository import listar_alertas_contenedores
    desde, hasta = _rango(params)
    filas = [("Incidente", f[0], f[1], None, f[3], f[4], f[5], f[6])
             for f in repo.incidentes_cliente(id_cliente, desde, hasta,
                                              params.get("severidad"), params.get("estado"))]
    contenedores = {c[0]: c[1] for c in repo.contenedores_cliente(id_cliente, desde, hasta)}
    inicio, fin = _instantes(desde, hasta)
    for alerta in listar_alertas_contenedores(list(contenedores), inicio, fin):
        if params.get("severidad") and str(alerta.get("severidad", "")).lower() != params["severidad"].lower():
            continue
        fecha = alerta.get("fecha")
        if fecha is not None and fecha.tzinfo is None:
            fecha = fecha.replace(tzinfo=timezone.utc)   # MongoDB guarda UTC
        filas.append(("Alerta IoT", fecha, alerta.get("envio_id"),
                      contenedores.get(alerta.get("contenedor_id")), alerta.get("tipo"),
                      alerta.get("severidad"), alerta.get("estado"), alerta.get("descripcion")))
    filas.sort(key=lambda f: f[1] or datetime.min.replace(tzinfo=timezone.utc))
    return Tabla("Incidentes y alertas de mis envíos",
                 ["Origen", "Fecha", "Envío", "Contenedor", "Tipo", "Severidad", "Estado", "Descripción"],
                 filas, "PostgreSQL (incidentes) + MongoDB (alertas de sus contenedores)")


@con_vacio("No hay envíos")
def generar_puntualidad(id_cliente, params, ahora=None):
    desde, hasta = _rango(params)
    filas = repo.puntualidad_cliente(id_cliente, desde, hasta, params.get("ruta"))
    retrasos = retrasos_por_envio([f[0] for f in filas])
    salida = []
    for (id_envio, origen, destino, p_origen, p_destino, estado, creado,
         estimada, entrega) in filas:
        resultado = situacion(estado, estimada, entrega, ahora)
        diferencia = None
        if resultado in ("A tiempo", "Tarde"):
            diferencia = horas(entrega - estimada)
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


@con_vacio("No hay tramos con operador asignado para sus contenedores")
def generar_operadores(id_cliente, params):
    from app.repositories.grafo_repository import operadores_de_contenedores_cliente
    desde, hasta = _rango(params)
    ids = repo.ids_envios_cliente(id_cliente, desde, hasta)
    filas = operadores_de_contenedores_cliente(id_cliente, ids, params.get("id_contenedor"))
    return Tabla("Operadores que llevaron mis contenedores",
                 ["Contenedor", "Envío", "Tramo", "Medio", "Origen", "Destino", "Salida", "Operador"],
                 [(f["contenedor"], f["id_envio"], f["id_tramo"], f["medio"], f["origen"],
                   f["destino"], (f["salida"] or "")[:16].replace("T", " "),
                   f["operador"] or "Sin asignar") for f in filas],
                 "Neo4j (grafo cliente-envío-contenedor-tramo-operador) + PostgreSQL (período)")


def limites_carga():
    """(temp. mínima, temp. máxima, humedad máxima) de las reglas de alerta activas."""
    from app.repositories.regla_alerta_repository import reglas_vigentes, umbral
    vigentes = reglas_vigentes()
    return (umbral(vigentes, "temperatura", "MIN", 2.0),
            umbral(vigentes, "temperatura", "MAX", 8.0),
            umbral(vigentes, "humedad", "MAX", 80.0))


@con_vacio("No hay contenedores con lecturas")
def generar_condiciones_carga(id_cliente, params):
    from app.repositories.lectura_iot_repository import consultar_lecturas_contenedor_periodo
    temp_min, temp_max, hum_max = limites_carga()
    desde, hasta = _rango(params)
    inicio, fin = _instantes(desde, hasta)
    filas = []
    for id_cont, codigo, tipo, id_envio, creado, terminado in repo.contenedores_cliente(
            id_cliente, desde, hasta, params.get("id_contenedor")):
        # Solo el tramo de tiempo en que el contenedor viajó para ESTE cliente.
        lecturas = consultar_lecturas_contenedor_periodo(
            id_cont, max(inicio, creado), min(fin, terminado))
        temps = [l.temperatura for l in lecturas if l.temperatura is not None]
        hums = [l.humedad for l in lecturas if l.humedad is not None]
        gps = [l for l in lecturas if l.gps_latitud is not None]
        fuera = sum(1 for t in temps if not temp_min <= t <= temp_max)
        fuera += sum(1 for h in hums if h > hum_max)
        filas.append((codigo, tipo, id_envio, len(lecturas),
                      min(temps) if temps else None, max(temps) if temps else None,
                      min(hums) if hums else None, max(hums) if hums else None, fuera,
                      f"{gps[0].gps_latitud:.4f}, {gps[0].gps_longitud:.4f}" if gps else None,
                      f"{gps[-1].gps_latitud:.4f}, {gps[-1].gps_longitud:.4f}" if gps else None))
    return Tabla("Condiciones de la carga en viaje",
                 ["Contenedor", "Tipo", "Envío", "Lecturas", "Temp. mín.", "Temp. máx.",
                  "Hum. mín.", "Hum. máx.", "Lecturas fuera de rango",
                  "Primera posición GPS", "Última posición GPS"],
                 filas, "Cassandra (lecturas_por_contenedor) + PostgreSQL (contenedores del cliente)",
                 [f"Fuera de rango: temperatura fuera de {temp_min:g} a {temp_max:g} °C "
                  f"o humedad mayor a {hum_max:g} %."])


@con_vacio("No hay envíos en curso")
def generar_predictivo(id_cliente, params):
    """Solo los envíos en curso de ESE cliente, según la última predicción."""
    from app.services.reportes_service import reporte_riesgo_envios
    tabla = reporte_riesgo_envios(id_cliente)
    columnas = [c for c in tabla.columnas if c != "Cliente"]
    tabla.filas = [tuple(v for c, v in zip(tabla.columnas, f) if c != "Cliente")
                   for f in tabla.filas]
    tabla.columnas = columnas
    tabla.titulo = "Riesgo de demora de mis envíos en curso"
    tabla.vacio = ""
    return tabla


GENERADORES = {
    "INCIDENTES": generar_incidentes,
    "PUNTUALIDAD": generar_puntualidad,
    "OPERADORES": generar_operadores,
    "CONDICIONES_CARGA": generar_condiciones_carga,
    "PREDICTIVO": generar_predictivo,
}


# ------------------------------------------------------------------ ciclo

def solicitar_reporte(id_cliente, id_usuario, tipo, formato, parametros, hoy_=None):
    """Solicita, genera y factura. Devuelve el reporte final (dict).

    Si la generación falla queda ERROR y no se factura. Si la facturación
    falla queda GENERADO (se puede reintentar con facturar_pendientes).
    """
    formato = str(formato).upper()
    if formato not in FORMATOS:
        raise ValueError("Formato inválido (CSV o PDF).")
    params = validar_parametros(tipo, parametros, hoy_)
    id_reporte = repo.crear_reporte(id_cliente, id_usuario, tipo, formato, params)
    logger.info("Reporte %s solicitado: cliente=%s tipo=%s", id_reporte, id_cliente, tipo)

    try:
        tabla = GENERADORES[tipo](id_cliente, params)
        reporte = repo.obtener_reporte(id_reporte)
        encabezado = ([f"Reporte N.º {id_reporte} - {reporte['cliente']}"]
                      + describir_parametros(params)
                      + [f"Generado: {datetime.now(ZONA):%d/%m/%Y %H:%M}"])
        ruta, hash_ = exportar(tabla, formato,
                               Path(CARPETA_REPORTES) / f"{id_reporte}_{tipo}", encabezado)
        repo.marcar_generado(id_reporte, str(ruta), len(tabla.filas), hash_)
    except Exception as error:
        logger.exception("Error al generar el reporte %s", id_reporte)
        repo.marcar_error(id_reporte, error)
        return repo.obtener_reporte(id_reporte)

    try:
        emitir_factura_reporte(id_reporte)
    except Exception:
        logger.exception("No se pudo facturar el reporte %s", id_reporte)
    return repo.obtener_reporte(id_reporte)


def facturar_pendientes():
    """Factura los reportes que quedaron GENERADOS. Devuelve (facturados, errores)."""
    facturados, errores = [], []
    for reporte in repo.listar_reportes(estado="GENERADO"):
        try:
            facturados.append(emitir_factura_reporte(reporte["id_reporte"]))
        except FacturaExistente:
            continue
        except Exception as error:
            errores.append((reporte["id_reporte"], str(error)))
    return facturados, errores


def reporte_del_cliente(id_reporte, id_cliente):
    """El reporte si es del cliente; si no, None (como si no existiera)."""
    reporte = repo.obtener_reporte(id_reporte)
    if reporte is None or reporte["id_cliente"] != id_cliente:
        return None
    return reporte
