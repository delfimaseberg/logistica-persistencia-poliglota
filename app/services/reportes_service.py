"""Reportes operativos, analíticos y rankings (usuarios internos).

Cada función devuelve una Tabla. Definiciones comunes (sin tolerancia):
- A tiempo: entrega <= mayor llegada estimada de los tramos.
- Tarde: entrega > esa llegada estimada.
- Demorado: no entregado ni cancelado y la llegada estimada ya pasó.
"""

from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from functools import wraps

from app.repositories import reportes_repository as repo
from app.utils.exportar_reportes import Tabla


def con_vacio(mensaje):
    """Mensaje claro cuando el reporte no tiene filas (lo completa la pantalla
    con 'para el cliente elegido' / 'en el período elegido')."""
    def decorar(funcion):
        @wraps(funcion)
        def envoltura(*args, **kwargs):
            tabla = funcion(*args, **kwargs)
            if not tabla.vacio:
                tabla.vacio = mensaje
            return tabla
        return envoltura
    return decorar


def horas(delta):
    return round(delta.total_seconds() / 3600, 1)


def situacion(estado, llegada_estimada, fecha_entrega, ahora=None):
    """A tiempo / Tarde / Demorado / En curso / Cancelado / Sin tramos."""
    ahora = ahora or datetime.now(timezone.utc)
    estado = str(estado or "").strip().casefold()
    if estado == "cancelado":
        return "Cancelado"
    if llegada_estimada is None:
        return "Sin tramos"
    if estado == "entregado" and fecha_entrega is not None:
        return "A tiempo" if fecha_entrega <= llegada_estimada else "Tarde"
    return "Demorado" if llegada_estimada < ahora else "En curso"


def tiempos_por_envio(ids_envios):
    """{id_envio: (primer EN_TRANSITO, ENTREGADO)} desde MongoDB."""
    from app.repositories.evento_repository import listar_eventos_envios
    if not ids_envios:
        return {}
    marcas = defaultdict(dict)
    for evento in listar_eventos_envios(list(ids_envios)):
        fecha = evento.get("fecha_hora")
        if fecha is not None and fecha.tzinfo is None:
            fecha = fecha.replace(tzinfo=timezone.utc)
        tipo = evento.get("tipo")
        id_envio = int(evento["envio_id"])
        if tipo == "EN_TRANSITO":
            anterior = marcas[id_envio].get("transito")
            if anterior is None or fecha < anterior:
                marcas[id_envio]["transito"] = fecha
        elif tipo == "ENTREGADO":
            marcas[id_envio]["entrega"] = fecha
    return {k: (v.get("transito"), v.get("entrega")) for k, v in marcas.items()}


def retrasos_por_envio(ids_envios):
    """{id_envio: (cantidad de eventos RETRASO, último motivo)} desde MongoDB."""
    from app.repositories.evento_repository import listar_eventos_envios
    if not ids_envios:
        return {}
    resultado = {}
    for evento in listar_eventos_envios(list(ids_envios)):
        if evento.get("tipo") != "RETRASO":
            continue
        id_envio = int(evento["envio_id"])
        cantidad, _ = resultado.get(id_envio, (0, None))
        motivo = (evento.get("detalle") or {}).get("motivo") or evento.get("descripcion")
        resultado[id_envio] = (cantidad + 1, motivo)
    return resultado


# ------------------------------------------------------------ 35

@con_vacio("No hay envíos")
def reporte_envios_por_pais(desde, hasta, id_cliente=None):
    return Tabla(
        "Envíos por país de destino",
        ["País destino", "Envíos", "Entregados", "En curso", "Cancelados", "Países de origen"],
        repo.envios_por_pais(desde, hasta, id_cliente),
        "PostgreSQL",
        ["Los envíos anteriores a la carga de países figuran como 'Sin dato'."],
    )


@con_vacio("No hay envíos")
def reporte_envios_por_estado(desde, hasta, id_cliente=None):
    return Tabla("Envíos por estado", ["Estado", "Envíos"],
                 repo.envios_por_estado(desde, hasta, id_cliente), "PostgreSQL")


@con_vacio("No hay envíos")
def reporte_envios_por_cliente(desde, hasta, id_cliente=None):
    return Tabla("Envíos por cliente",
                 ["Cliente", "País del cliente", "Envíos", "Entregados", "En curso", "Cancelados"],
                 repo.envios_por_cliente(desde, hasta, id_cliente), "PostgreSQL")


@con_vacio("No hay envíos demorados")
def reporte_envios_demorados(id_cliente=None):
    filas = repo.envios_demorados(id_cliente)
    retrasos = retrasos_por_envio([f[0] for f in filas])
    return Tabla(
        "Envíos demorados (llegada estimada vencida)",
        ["Envío", "Cliente", "Ruta", "Países", "Estado", "Llegada estimada",
         "Horas de demora", "Retrasos informados", "Último motivo"],
        [(f[0], f[1], f"{f[2]} -> {f[3]}", f"{f[4] or 'Sin dato'} -> {f[5] or 'Sin dato'}",
          f[6], f[7], round(float(f[8]), 1), *retrasos.get(f[0], (0, None)))
         for f in filas],
        "PostgreSQL + MongoDB (eventos RETRASO)",
    )


@con_vacio("No hay incidentes abiertos")
def reporte_incidentes_abiertos(id_cliente=None):
    return Tabla(
        "Incidentes abiertos",
        ["Incidente", "Envío", "Cliente", "Ruta", "Tipo", "Severidad", "Estado",
         "Fecha", "Días abierto"],
        [(*f[:8], round(float(f[8]), 1)) for f in repo.incidentes_abiertos(id_cliente)],
        "PostgreSQL",
    )


# ------------------------------------------------------------ 36 / 38

def _entregados_con_tiempos(desde, hasta, id_cliente=None):
    filas = repo.envios_entregados(desde, hasta, id_cliente)
    marcas = tiempos_por_envio([f[0] for f in filas])
    resultado = []
    for f in filas:
        transito, entrega_evento = marcas.get(f[0], (None, None))
        total_h = horas(f[7] - f[6])
        transito_h = horas(f[7] - transito) if transito else None
        resultado.append({
            "id_envio": f[0], "cliente": f[1], "ruta": f"{f[2]} -> {f[3]}",
            "medios": list(f[9] or []), "total_h": total_h, "transito_h": transito_h,
            "estimada": f[8], "entrega": f[7],
        })
    return resultado


def _min_max(valores):
    valores = [v for v in valores if v is not None]
    return (min(valores), max(valores)) if valores else (None, None)


@con_vacio("No hay envíos entregados")
def reporte_tiempos_extremos(desde, hasta, id_cliente=None):
    por_cliente = defaultdict(list)
    for envio in _entregados_con_tiempos(desde, hasta, id_cliente):
        por_cliente[envio["cliente"]].append(envio)
    filas = []
    for cliente, envios in sorted(por_cliente.items()):
        tmin, tmax = _min_max([e["total_h"] for e in envios])
        rmin, rmax = _min_max([e["transito_h"] for e in envios])
        filas.append((cliente, len(envios), tmin, tmax, rmin, rmax))
    return Tabla(
        "Tiempos máximos y mínimos de envío por cliente (horas)",
        ["Cliente", "Entregados", "Total mín.", "Total máx.", "Tránsito mín.", "Tránsito máx."],
        filas, "PostgreSQL (creación y entrega) + MongoDB (EN_TRANSITO -> ENTREGADO)",
        ["Total = creación del envío -> entrega. Tránsito = primer evento EN_TRANSITO -> entrega."],
    )


def _promedio(valores):
    valores = [v for v in valores if v is not None]
    return round(sum(valores) / len(valores), 1) if valores else None


@con_vacio("No hay envíos entregados")
def reporte_tiempos_promedio(desde, hasta, id_cliente=None):
    envios = _entregados_con_tiempos(desde, hasta, id_cliente)
    grupos = []
    for etiqueta, clave in (("Cliente", lambda e: [e["cliente"]]),
                            ("Ruta", lambda e: [e["ruta"]]),
                            ("Medio", lambda e: e["medios"] or ["Sin tramos"])):
        acumulado = defaultdict(list)
        for envio in envios:
            for valor in clave(envio):
                acumulado[valor].append(envio)
        for valor, lista in sorted(acumulado.items()):
            grupos.append((etiqueta, valor, len(lista),
                           _promedio([e["total_h"] for e in lista]),
                           _promedio([e["transito_h"] for e in lista])))
    return Tabla(
        "Tiempos promedio de entrega (horas)",
        ["Agrupado por", "Valor", "Entregados", "Promedio total", "Promedio tránsito"],
        grupos, "PostgreSQL + MongoDB",
        ["Un envío con tramos de varios medios cuenta en cada medio."],
    )


# ------------------------------------------------------------ 37

@con_vacio("No hay envíos")
def reporte_promedio_incidentes(desde, hasta, id_cliente=None):
    filas = []
    for agrupacion, etiqueta in (("pais", "País destino"), ("estado", "Estado"),
                                 ("cliente", "Cliente")):
        for grupo, envios, incidentes, promedio in repo.promedio_incidentes(
                desde, hasta, agrupacion, id_cliente):
            filas.append((etiqueta, grupo, envios, incidentes, promedio))
    return Tabla("Promedio de incidentes por envío",
                 ["Agrupado por", "Valor", "Envíos", "Incidentes", "Promedio"],
                 filas, "PostgreSQL")


# ------------------------------------------------------------ 39

@con_vacio("No hay tramos facturados ni facturas de operadores")
def reporte_costos_por_medio(desde, hasta):
    ventas = {m: (n, v) for m, n, v in repo.ventas_por_medio(desde, hasta)}
    costos = {m: (n, v) for m, n, v in repo.costos_operadores_por_medio(desde, hasta)}
    filas = []
    for medio in sorted(set(ventas) | set(costos)):
        lineas, vendido = ventas.get(medio, (0, Decimal("0")))
        facturas, costo = costos.get(medio, (0, Decimal("0")))
        es_base = medio not in costos and medio.startswith("Cargo base")
        margen = vendido - costo
        porcentaje = round(float(margen / vendido * 100), 1) if vendido else None
        filas.append((medio, lineas, vendido, facturas, None if es_base else costo,
                      margen, porcentaje))
    return Tabla(
        "Costos por tipo de transporte: lo que cobramos vs lo que nos cobran",
        ["Medio", "Tramos facturados", "Facturado a clientes (neto)",
         "Facturas de operadores", "Costo de operadores", "Margen", "Margen %"],
        filas, "PostgreSQL (factura_detalle y factura_recibida)",
        ["Facturado: líneas de las facturas a clientes, sin IVA. Costo: facturas "
         "recibidas de operadores por tramo, en el período de emisión."],
    )


# ------------------------------------------------------------ 27 / 28 / 31

@con_vacio("No hay envíos")
def reporte_ranking_rutas(desde, hasta):
    return Tabla(
        "Ranking de rutas con más incidentes",
        ["Ruta", "Países", "Envíos", "Incidentes", "Abiertos", "Graves"],
        repo.ranking_rutas_incidentes(desde, hasta), "PostgreSQL",
    )


@con_vacio("No hay envíos")
def reporte_ranking_volumen(desde, hasta):
    return Tabla(
        "Ranking de clientes por volumen transportado",
        ["Cliente", "País", "Envíos", "Contenedores", "Capacidad (m3)", "Peso (kg)"],
        repo.ranking_clientes_volumen(desde, hasta), "PostgreSQL",
        ["Ordenado por peso declarado en las partidas de carga y, a igual peso, "
         "por capacidad de contenedores. No incluye envíos cancelados."],
    )


@con_vacio("No hay envíos entregados")
def reporte_desempeno(desde, hasta, id_cliente=None, ahora=None):
    from app.repositories.grafo_repository import operadores_por_envio
    filas = repo.envios_entregados(desde, hasta, id_cliente)
    operadores = operadores_por_envio([f[0] for f in filas])

    grupos = defaultdict(lambda: {"a_tiempo": 0, "tarde": 0, "demoras": []})
    for f in filas:
        resultado = situacion("Entregado", f[8], f[7], ahora)
        if resultado not in ("A tiempo", "Tarde"):
            continue
        claves = [("Ruta", f"{f[2]} -> {f[3]}"),
                  ("Mes", f[7].strftime("%Y-%m"))]
        claves += [("Operador", nombre) for nombre in
                   sorted({op[1] for op in operadores.get(f[0], [])})]
        for clave in claves:
            grupo = grupos[clave]
            if resultado == "A tiempo":
                grupo["a_tiempo"] += 1
            else:
                grupo["tarde"] += 1
                grupo["demoras"].append(horas(f[7] - f[8]))

    tabla = []
    for (tipo, valor), g in sorted(grupos.items()):
        total = g["a_tiempo"] + g["tarde"]
        tabla.append((tipo, valor, total, g["a_tiempo"], g["tarde"],
                      round(g["a_tiempo"] * 100 / total, 1),
                      _promedio(g["demoras"])))
    return Tabla(
        "Desempeño histórico: a tiempo vs tarde",
        ["Agrupado por", "Valor", "Entregados", "A tiempo", "Tarde", "% a tiempo",
         "Demora promedio de los tarde (h)"],
        tabla, "PostgreSQL + Neo4j (operadores de cada envío)",
        ["Un envío con varios operadores cuenta para cada operador."],
    )


# ------------------------------------------------------------ 34 predictivos

def _principal_factor(prediccion):
    factores = prediccion.get("factores_probabilidad") or []
    if not factores:
        return "Sin factores de demora"
    mayor = max(factores, key=lambda f: f["probabilidad"])
    return f"{mayor['factor']} ({mayor['probabilidad']:.0%})"


def reporte_riesgo_envios(id_cliente=None):
    """Envíos en curso por nivel de riesgo, según la última predicción diaria.

    Bases: PostgreSQL (envíos en curso) + MongoDB (predicciones_riesgo).
    """
    from app.repositories.predicciones_repository import ultimas_predicciones

    envios = repo.envios_en_curso(id_cliente)
    predicciones = ultimas_predicciones([e[0] for e in envios])
    filas = []
    for id_envio, cliente, origen, destino, estado in envios:
        p = predicciones.get(id_envio)
        if p is None:
            filas.append((id_envio, cliente, f"{origen} -> {destino}", estado,
                          "Sin predicción", None, None, None, None, None))
            continue
        fecha = p.get("fecha_calculo")
        if fecha is not None and fecha.tzinfo is None:
            fecha = fecha.replace(tzinfo=timezone.utc)
        from app.services.predicciones_service import texto_probabilidad
        probabilidad = p.get("probabilidad_demora")
        filas.append((id_envio, cliente, f"{origen} -> {destino}", estado,
                      p.get("nivel_riesgo"),
                      texto_probabilidad(p),
                      p.get("riesgo_climatico"),
                      p.get("riesgo_operativo") or p.get("nivel_riesgo_operativo"),
                      _principal_factor(p) if probabilidad is not None else "Sin dato",
                      fecha))
    orden = {"ALTO": 0, "MEDIO": 1, "BAJO": 2}

    def clave(fila):
        p = predicciones.get(fila[0]) or {}
        return (orden.get(fila[4], 3), -(p.get("probabilidad_demora") or 0), fila[0])

    filas.sort(key=clave)
    tabla = Tabla(
        "Riesgo de demora de los envíos en curso",
        ["Envío", "Cliente", "Ruta", "Estado", "Nivel de riesgo", "Probabilidad de demora",
         "Riesgo climático", "Riesgo operativo", "Principal factor", "Calculado"],
        filas, "PostgreSQL + MongoDB (predicciones de riesgo)",
        ["Según la última predicción de cada envío (se recalcula todos los días). "
         "La probabilidad combina el historial de atrasos de la ruta, las alertas "
         "climáticas, los incidentes abiertos y el plazo."],
    )
    tabla.vacio = "No hay envíos en curso"
    return tabla


def reporte_rutas_atraso():
    """Rutas que suelen atrasarse: PostgreSQL (entregas) + MongoDB (RETRASO)."""
    from app.services.predicciones_service import MIN_ENVIOS_HISTORIAL, historial_rutas

    historial = historial_rutas()
    filas = []
    for datos in historial["rutas"].values():
        porcentaje = round(datos["atrasados"] * 100 / datos["envios"], 1)
        filas.append((datos["ruta"], datos["envios"], datos["atrasados"], porcentaje,
                       "Sí" if datos["envios"] >= MIN_ENVIOS_HISTORIAL else "No (se usa la general)"))
    filas.sort(key=lambda f: (-f[3], -f[1], f[0]))
    general = historial["general"]
    notas = ["Atrasado: entregado después de la llegada estimada o con un retraso informado."]
    if general["envios"]:
        notas.append(f"Tasa general: {general['atrasados']} de {general['envios']} "
                     f"({general['atrasados'] * 100 / general['envios']:.1f} %).")
    tabla = Tabla("Rutas que suelen atrasarse",
                  ["Ruta", "Entregados", "Atrasados", "% de atraso", "Historial propio"],
                  filas, "PostgreSQL + MongoDB (eventos RETRASO)", notas)
    tabla.vacio = "Todavía no hay envíos entregados para calcular el historial"
    return tabla


def reporte_clima_vigente(ahora=None):
    """Alertas climáticas vigentes y envíos en curso afectados.

    Bases: MongoDB (alertas_climaticas) + PostgreSQL (envíos y tramos).
    """
    from app.repositories.alerta_climatica_repository import listar_alertas_climaticas
    from app.repositories.predicciones_repository import obtener_datos_riesgo
    from app.services.predicciones_service import alertas_que_afectan

    ahora = ahora or datetime.now(timezone.utc)
    alertas = listar_alertas_climaticas(ahora=ahora)
    afectados = defaultdict(list)
    for envio in repo.envios_en_curso():
        datos = obtener_datos_riesgo(envio[0])
        for alerta in alertas_que_afectan(datos, alertas, ahora):
            afectados[alerta["_id"]].append(str(envio[0]))
    filas = [(a["fenomeno"], a["ubicacion"], a["severidad"],
              datetime.fromisoformat(a["fecha_desde"]).date(),
              datetime.fromisoformat(a["fecha_hasta"]).date(),
              ", ".join(afectados.get(a["_id"], [])) or "Ninguno")
             for a in alertas]
    tabla = Tabla("Alertas climáticas vigentes y envíos afectados",
                  ["Fenómeno", "Ubicación", "Severidad", "Desde", "Hasta", "Envíos afectados"],
                  filas, "MongoDB (alertas_climaticas) + PostgreSQL (tramos)")
    tabla.vacio = "No hay alertas climáticas vigentes"
    return tabla
