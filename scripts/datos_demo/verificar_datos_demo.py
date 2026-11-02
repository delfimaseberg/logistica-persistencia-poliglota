"""Verifica que cada funcionalidad tenga datos de ejemplo con resultado.

Cada verificación indica el número de requisito (1 a 40) al que corresponde,
la base que consulta y lo que encontró. Al final resume qué requisitos tienen
resultado.

Solo lectura salvo con --cerrar-octubre (que cierra el período 2026-10 con
fecha simulada 01/11; usar solo en una base descartable).

Uso:
    python scripts\\datos_demo\\verificar_datos_demo.py [--solo-postgres] [--cerrar-octubre]
"""

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.database.postgres_connection import get_postgres_connection  # noqa: E402

resultados = []


def q(sql, params=()):
    with get_postgres_connection() as c, c.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def requisito(numero, nombre, valor, ok, base="PG"):
    resultados.append((numero, nombre, base, valor, ok))


def verificar_postgres():
    n = lambda sql, p=(): q(sql, p)[0][0]  # noqa: E731
    requisito(1, "ABM Clientes", f"{n('SELECT count(*) FROM cliente')} clientes, "
          f"{n('SELECT count(DISTINCT pais) FROM cliente')} países",
          n("SELECT count(DISTINCT pais) FROM cliente") >= 3)
    partes = q("""SELECT count(*) FILTER (WHERE id_cliente IS NOT NULL),
                         count(*) FILTER (WHERE id_proveedor IS NOT NULL),
                         count(*) FILTER (WHERE id_operador IS NOT NULL),
                         count(*) FILTER (WHERE num_nonnulls(id_cliente, id_proveedor, id_operador) = 0)
                  FROM usuario""")[0]
    requisito(2, "ABM Usuarios y Roles", f"usuarios cliente/proveedor/operador/internos = {partes}",
          all(x > 0 for x in partes))
    requisito(4, "ABM Proveedores", f"{n('SELECT count(*) FROM proveedor')} proveedores",
          n("SELECT count(*) FROM proveedor") >= 2)
    requisito(5, "ABM Operadores", f"{n('SELECT count(*) FROM operador_logistico')} operadores, "
          f"{n('SELECT count(*) FROM tramo WHERE id_operador IS NOT NULL')} tramos con operador",
          n("SELECT count(*) FROM operador_logistico") >= 2)
    requisito(6, "Envíos -> contenedores -> sensores",
          f"{n('SELECT count(*) FROM envio_contenedor')} asociaciones, "
          f"{n('SELECT count(*) FROM sensor_iot')} sensores",
          n("SELECT count(*) FROM envio_contenedor") >= 10)
    tarifas = n("SELECT count(*) FROM regla_tarifaria_version WHERE estado = 'APROBADA'")
    requisito(9, "Reglas (tarifa estándar)", f"{tarifas} regla aprobada", tarifas >= 1)
    por_envio = q("""SELECT count(*) FILTER (WHERE origen_emision = 'ENVIO_AUTOMATICA'),
                            count(*) FILTER (WHERE origen_emision = 'ENVIO_MANUAL')
                     FROM factura WHERE id_envio IS NOT NULL""")[0]
    requisito(10, "Facturación y cobros (clientes)", f"facturas por envío automáticas/manuales = {por_envio}",
          por_envio[0] > 0 and por_envio[1] > 0)
    requisito(12, "Facturación automática", f"{por_envio[0]} automáticas", por_envio[0] > 0)
    pagos = q("""SELECT count(*) FILTER (WHERE estado = 'Pagada'), count(*) FILTER (WHERE estado = 'Parcial'),
                        count(*) FILTER (WHERE estado = 'Pendiente') FROM factura WHERE id_envio IS NOT NULL""")[0]
    requisito(13, "Registro de pagos", f"facturas por envío pagadas/parciales/pendientes = {pagos}",
          pagos[0] > 0 and pagos[1] > 0)
    concilia = n("""SELECT count(*) FROM cuenta_corriente cc
                    JOIN apertura_cuenta_corriente a USING (id_cliente)
                    WHERE cc.saldo <> a.saldo_inicial + (
                        SELECT COALESCE(sum(importe_firmado), 0) FROM movimiento_cuenta_corriente m
                        WHERE m.id_cliente = cc.id_cliente AND m.fecha_contable >= a.fecha_vigencia)""")
    requisito(14, "Gestión de cuentas corrientes",
          f"{n('SELECT count(*) FROM cuenta_corriente')} cuentas; no concilian: {concilia}", concilia == 0)
    cierres = n("SELECT count(*) FROM cierre_cuenta_corriente WHERE periodo = DATE '2026-10-01'")
    aperturas = n("SELECT count(*) FROM apertura_cuenta_corriente")
    requisito(15, "Cierre mensual", f"{aperturas} aperturas; cierres de 10/2026: {cierres}",
          aperturas == n("SELECT count(*) FROM cuenta_corriente"))
    terceros = q("""SELECT count(*) FILTER (WHERE id_operador IS NOT NULL), count(*) FILTER (WHERE id_proveedor IS NOT NULL),
                           count(*) FILTER (WHERE estado IN ('Pendiente','Parcial') AND fecha_vencimiento < CURRENT_DATE)
                    FROM factura_recibida""")[0]
    requisito(16, "CC proveedores y operadores",
          f"facturas operador/proveedor = {terceros[:2]}, vencidas impagas = {terceros[2]}",
          terceros[0] > 0 and terceros[1] > 0 and terceros[2] > 0)
    entregados = q("""SELECT count(*), count(*) FILTER (WHERE fecha_entrega > (SELECT max(t.fecha_estimada_llegada)
                      FROM tramo t WHERE t.id_envio = e.id_envio)) FROM envio e WHERE estado = 'Entregado'""")[0]
    requisito(24, "Trayectos / seguimiento", f"{entregados[0]} entregados con fecha real, {entregados[1]} tarde",
          entregados[0] >= 5 and entregados[1] >= 1)
    demorados = n("""SELECT count(*) FROM (SELECT e.id_envio FROM envio e JOIN tramo t USING (id_envio)
                     WHERE lower(e.estado) NOT IN ('entregado','cancelado')
                     GROUP BY e.id_envio HAVING max(t.fecha_estimada_llegada) < now()) x""")
    requisito(35, "Reporte de envíos demorados (consulta existente)", f"{demorados} demorado(s)", demorados >= 1)
    incid = q("""SELECT count(*), count(*) FILTER (WHERE i.estado = 'Abierto'),
                        count(DISTINCT e.origen || '->' || e.destino)
                 FROM incidente i JOIN envio e USING (id_envio)""")[0]
    requisito(25, "Incidentes", f"total/abiertos/rutas con incidentes = {incid}", incid[1] >= 1)
    requisito(27, "Datos para ranking de rutas con incidentes",
          f"{incid[2]} rutas con incidentes", incid[2] >= 2)
    paises = n("SELECT count(DISTINCT c.pais) FROM envio e JOIN cliente c USING (id_cliente)")
    requisito(28, "Ranking de clientes (consulta existente)", f"envíos de {paises} países", paises >= 3)
    medios = q("""SELECT medio_transporte, sum(importe) FROM factura_detalle
                  WHERE concepto = 'TRAMO' GROUP BY 1 ORDER BY 1""")
    requisito(39, "Datos para costos por tipo de transporte", str(medios), len(medios) == 3)


def verificar_nosql():
    from pymongo import MongoClient  # noqa: F401  (conexión vía la app)
    from app.database.mongo_connection import get_mongo_database
    from app.repositories.lectura_iot_repository import abrir_conexion, cerrar_conexion
    from app.database.neo4j_connection import abrir_sesion_neo4j

    db = get_mongo_database()
    ev = db.eventos_logisticos.count_documents({})
    entregados = db.eventos_logisticos.count_documents({"tipo": "ENTREGADO"})
    requisito(17, "Monitoreo: eventos", f"{ev} eventos ({entregados} ENTREGADO)", entregados >= 8, "Mongo")
    alertas = list(db.alertas.aggregate([{"$group": {"_id": "$tipo", "n": {"$sum": 1}}}]))
    tipos = {a["_id"]: a["n"] for a in alertas}
    requisito(23, "Alertas de estado de sensores", str(tipos),
          any("transmisi" in str(k) or "lecturas" in str(k) for k in tipos), "Mongo")
    requisito(32, "Anomalías de temperatura", f"Temperatura alta: {tipos.get('Temperatura alta', 0)}",
          tipos.get("Temperatura alta", 0) >= 1, "Mongo")
    requisito(40, "Mensajería con las partes",
          f"{db.mensajes.count_documents({})} mensajes, {db.grupos_trabajo.count_documents({})} grupos",
          db.mensajes.count_documents({}) >= 6, "Mongo")
    requisito(29, "Predicción de atrasos", f"{db.predicciones_riesgo.count_documents({})} predicciones",
          db.predicciones_riesgo.count_documents({}) > 0, "Mongo")

    cluster, s = abrir_conexion()
    try:
        meses = sorted({r.anio_mes for r in s.execute("SELECT DISTINCT contenedor_id, anio_mes FROM lecturas_por_contenedor")})
        gps = sum(1 for r in s.execute("SELECT gps_latitud FROM lecturas_por_contenedor") if r.gps_latitud is not None)
    finally:
        cerrar_conexion(cluster, s)
    requisito(18, "Registro continuo de lecturas IoT", f"particiones por mes: {meses}", len(meses) >= 3, "Cassandra")
    requisito(21, "Posiciones GPS", f"{gps} lecturas con GPS", gps > 50, "Cassandra")

    with abrir_sesion_neo4j() as ses:
        rp = ses.run("MATCH ()-[r:REALIZADO_POR]->(:Operador) RETURN count(r) AS c").single()["c"]
        env = ses.run("MATCH (e:Envio) RETURN count(e) AS c").single()["c"]
    pg_env = q("SELECT count(*) FROM envio")[0][0]
    requisito(30, "Red clientes-operadores-envíos", f"{env}/{pg_env} envíos en el grafo, {rp} REALIZADO_POR",
          env == pg_env and rp > 0, "Neo4j")


def verificar_reportes():
    """Corre cada reporte real (todas las bases) y exige resultado."""
    from app.services import reportes_service as rs
    desde, hasta = date(2026, 1, 1), date.today()

    def correr(numero, nombre, tabla, condicion=lambda t: bool(t.filas)):
        requisito(numero, f"Reporte: {nombre}", f"{len(tabla.filas)} filas [{tabla.fuente}]",
              condicion(tabla), "Reporte")
        return tabla

    pais = correr(35, "envíos por país de destino", rs.reporte_envios_por_pais(desde, hasta),
                  lambda t: sum(1 for f in t.filas if f[0] != "Sin dato") >= 4)
    correr(35, "envíos por estado", rs.reporte_envios_por_estado(desde, hasta))
    correr(35, "envíos por cliente", rs.reporte_envios_por_cliente(desde, hasta),
           lambda t: len(t.filas) >= 5)
    correr(35, "envíos demorados", rs.reporte_envios_demorados(),
           lambda t: any(f[7] >= 1 for f in t.filas))      # con RETRASO de MongoDB
    correr(35, "incidentes abiertos", rs.reporte_incidentes_abiertos())
    correr(36, "tiempos máx./mín. por cliente", rs.reporte_tiempos_extremos(desde, hasta),
           lambda t: any(f[4] is not None for f in t.filas))   # tránsito desde MongoDB
    correr(37, "promedio de incidentes", rs.reporte_promedio_incidentes(desde, hasta),
           lambda t: sum(1 for f in t.filas if f[0] == "País destino" and f[3] > 0) >= 2)
    correr(38, "tiempos promedio de entrega", rs.reporte_tiempos_promedio(desde, hasta),
           lambda t: {f[0] for f in t.filas} == {"Cliente", "Ruta", "Medio"})
    correr(39, "costos por tipo de transporte", rs.reporte_costos_por_medio(desde, hasta),
           lambda t: sum(1 for f in t.filas if f[2] and f[4]) >= 2)
    correr(27, "ranking de rutas con incidentes", rs.reporte_ranking_rutas(desde, hasta),
           lambda t: len(t.filas) >= 3)
    correr(28, "ranking de clientes por volumen", rs.reporte_ranking_volumen(desde, hasta),
           lambda t: sum(1 for f in t.filas if f[5] > 0) >= 4)
    correr(31, "desempeño histórico", rs.reporte_desempeno(desde, hasta),
           lambda t: sum(1 for f in t.filas if f[0] == "Operador") >= 2
           and any(f[4] > 0 for f in t.filas))

    reportes = q("""SELECT r.tipo, r.formato, r.estado, f.id_factura IS NOT NULL,
                           m.importe_firmado = f.total
                    FROM reporte r
                    LEFT JOIN factura f ON f.id_reporte = r.id_reporte
                    LEFT JOIN movimiento_cuenta_corriente m
                      ON m.tipo_origen = 'FACTURA' AND m.referencia_origen = f.id_factura::text""")
    ok = (len(reportes) >= 3 and all(r[2] == "FACTURADO" and r[3] and r[4] for r in reportes)
          and {r[1] for r in reportes} == {"CSV", "PDF"})
    requisito(11, "Solicitud de reportes (cliente e interno)",
          f"{len(reportes)} reportes: {[(r[0], r[1], r[2]) for r in reportes]}", ok, "Reporte")
    requisito(33, "Reportes cobrables facturados con su movimiento",
          f"tipos {sorted({r[0] for r in reportes})}", ok and len({r[0] for r in reportes}) >= 3,
          "Reporte")


def verificar_sesiones_sensores_y_envios_postgres():
    """PostgreSQL: sesiones, reglas de alerta, contenedores y sensores, países y
    partidas de carga de los envíos y reporte predictivo cobrable."""
    n = lambda sql, p=(): q(sql, p)[0][0]  # noqa: E731
    sesiones = q("""SELECT count(*) FILTER (WHERE estado = 'ACTIVA'),
                           count(*) FILTER (WHERE cerrada_por IS NOT NULL
                                              AND cerrada_por <> id_usuario)
                    FROM sesion""")[0]
    requisito(3, "Sesiones: listar y cerrar sesiones ajenas",
          f"activas = {sesiones[0]}, cerradas por un administrador = {sesiones[1]}", sesiones[1] >= 1)
    activas = n("SELECT count(*) FROM regla_alerta WHERE activa")
    variables = n("SELECT count(DISTINCT variable) FROM regla_alerta WHERE activa")
    requisito(9, "Reglas de alerta configurables (ABM)",
          f"{activas} reglas activas de {variables} variables", activas >= 8 and variables == 7)
    contenedores = q("""SELECT count(*) FROM envio_contenedor ec JOIN envio e USING (id_envio)
                        WHERE e.estado NOT IN ('Entregado', 'Cancelado')""")[0][0]
    requisito(7, "Contenedores de envíos en curso", f"{contenedores} asociaciones", contenedores >= 5)
    sensores = q("""SELECT count(*) FILTER (WHERE estado = 'Activo'),
                           count(*) FILTER (WHERE estado = 'Inactivo'),
                           count(*) FILTER (WHERE motivo_inactivo LIKE 'Entrega del envío %%')
                    FROM sensor_iot""")[0]
    requisito(8, "Sensores por contenedor (activos/inactivos/apagados por entrega)", str(sensores),
          sensores[0] > 0 and sensores[2] >= 24)
    activos_entregados = n("""SELECT count(*) FROM sensor_iot s
                              JOIN envio_contenedor ec ON ec.id_contenedor = s.id_contenedor
                              JOIN envio e ON e.id_envio = ec.id_envio
                              WHERE e.estado = 'Entregado' AND s.estado = 'Activo'""")
    requisito(22, "Control de estado: sensores de envíos entregados inactivos",
          f"sensores activos en envíos entregados: {activos_entregados}", activos_entregados == 0)
    sin_pais = n("SELECT count(*) FROM envio WHERE pais_origen IS NULL OR pais_destino IS NULL")
    requisito(35, "Envíos con país de origen y destino", f"sin país: {sin_pais}", sin_pais == 0)
    from app.repositories.tarifas_repository import listar_cargas_envio
    id_envio = n("SELECT min(id_envio) FROM envio_carga")
    cargas = listar_cargas_envio(id_envio) if id_envio else []
    requisito(10, "Partidas de carga de un envío (listar_cargas_envio)",
          f"envío {id_envio}: {len(cargas)} partida(s) con descripción del tipo",
          bool(cargas) and all(c[2] for c in cargas))
    pred = q("""SELECT r.estado, f.id_factura, f.total FROM reporte r
                LEFT JOIN factura f ON f.id_reporte = r.id_reporte
                WHERE r.tipo = 'PREDICTIVO'""")
    requisito(34, "Reporte predictivo cobrable (cliente)", str(pred),
          bool(pred) and all(p[0] == "FACTURADO" and p[1] for p in pred), "Reporte")


def verificar_alertas_predicciones_y_lecturas():
    """MongoDB y Cassandra: fallas de sensor, mensajes por alerta, predicciones,
    reportes predictivos internos, lecturas históricas y recorrido GPS."""
    from datetime import datetime, timezone
    from app.database.mongo_connection import get_mongo_database
    from app.repositories.alerta_climatica_repository import listar_alertas_climaticas
    from app.repositories.lectura_iot_repository import consultar_lecturas_sensor_db
    from app.repositories.recorrido_repository import consultar_gps_contenedor
    from app.services import reportes_service as rs
    from app.services.deteccion_sensores import FALLA_CONGELADA, FALLA_SALTO, FALLA_VALOR

    db = get_mongo_database()
    fallas = {t: db.alertas.count_documents({"tipo": t})
              for t in (FALLA_VALOR, FALLA_CONGELADA, FALLA_SALTO)}
    atendidas = db.alertas.count_documents({"nota_atencion": "contenedor ya entregado"})
    requisito(23, "Fallas de sensor (imposible, congelado, salto) y alertas viejas atendidas",
          f"{fallas}; atendidas por contenedor entregado: {atendidas}",
          all(v >= 1 for v in fallas.values()) and atendidas >= 1, "Mongo")

    mensajes = db.mensajes.count_documents({"tipo": "Alerta"})
    sin_mensajes = db.alertas.count_documents({"mensajes_emitidos": False})
    duplicados = list(db.mensajes.aggregate([
        {"$match": {"tipo": "Alerta"}},
        {"$group": {"_id": {"a": "$alerta_id", "d": "$destinatario_id"}, "n": {"$sum": 1}}},
        {"$match": {"n": {"$gt": 1}}}]))
    internos = {f[0] for f in q("""SELECT id_usuario FROM usuario WHERE estado = 'ACTIVO'
                                   AND num_nonnulls(id_cliente, id_proveedor, id_operador) = 0""")}
    destinatarios = set(db.mensajes.distinct("destinatario_id", {"tipo": "Alerta"}))
    requisito(26, "Alertas con mensaje a internos y al cliente",
          f"{mensajes} mensajes de alerta; a internos: {bool(destinatarios & internos)}, "
          f"a clientes: {bool(destinatarios - internos)}; pendientes: {sin_mensajes}; "
          f"duplicados: {len(duplicados)}",
          mensajes > 0 and destinatarios & internos and destinatarios - internos
          and sin_mensajes == 0 and not duplicados, "Mongo")

    hoy = datetime.now(timezone.utc)
    vigentes = listar_alertas_climaticas(ahora=hoy)
    en_curso = [f[0] for f in q("""SELECT id_envio FROM envio
                                  WHERE estado NOT IN ('Entregado', 'Cancelado')""")]
    from app.repositories.predicciones_repository import ultimas_predicciones
    ultimas = ultimas_predicciones(en_curso)
    v4 = [p for p in ultimas.values() if p.get("metodo") == "reglas_heuristicas_v4"]
    con_clima = {p["envio_id"]: p["riesgo_climatico"] for p in v4
                 if p.get("riesgo_climatico") not in ("SIN ALERTAS", "NO EVALUADO", "NO APLICA")}
    con_historial = sum(1 for p in v4 if (p.get("historial_ruta") or {}).get("fuente") == "ruta")
    campos = all(all(k in p for k in ("envio_id", "riesgo_climatico", "riesgo_operativo",
                                       "probabilidad_demora", "fecha_calculo")) for p in v4)
    requisito(29, "Predicción: clima + rutas que se atrasan + probabilidad",
          f"{len(v4)}/{len(en_curso)} envíos con predicción v4; clima: {con_clima}; "
          f"con historial propio de la ruta: {con_historial}; alertas climáticas vigentes: {len(vigentes)}",
          len(v4) == len(en_curso) and con_clima and con_historial >= 1 and campos, "Mongo")

    tablas = [rs.reporte_riesgo_envios(), rs.reporte_rutas_atraso(), rs.reporte_clima_vigente()]
    afectados = [f for f in tablas[2].filas if f[5] != "Ninguno"]
    requisito(34, "Reportes predictivos internos (riesgo, rutas, clima)",
          f"filas = {[len(t.filas) for t in tablas]}; alertas con envíos afectados: {len(afectados)}",
          all(t.filas for t in tablas) and afectados, "Reporte")

    id_sensor = q("SELECT min(id_sensor) FROM sensor_iot")[0][0]
    historicas = consultar_lecturas_sensor_db(id_sensor, "2026-10", 50)
    requisito(19, "Consulta histórica de lecturas por sensor",
          f"sensor {id_sensor}, 10/2026: {len(historicas)} lecturas", len(historicas) > 0, "Cassandra")
    id_cont = q("""SELECT ec.id_contenedor FROM envio_contenedor ec JOIN envio e USING (id_envio)
                   WHERE e.estado = 'Entregado' ORDER BY e.id_envio LIMIT 1""")[0][0]
    gps = consultar_gps_contenedor(id_cont, ["2026-08", "2026-09", "2026-10"])
    requisito(20, "Recorrido de un contenedor (GPS)", f"contenedor {id_cont}: {len(gps)} posiciones",
          len(gps) >= 2, "Cassandra")


def resumen_requisitos():
    """Estado por requisito: OK si todas sus verificaciones dieron resultado."""
    por_requisito = {}
    for numero, _, _, _, ok in resultados:
        por_requisito.setdefault(numero, []).append(ok)
    sin_verificar = [n for n in range(1, 41) if n not in por_requisito]
    con_falta = sorted(n for n, oks in por_requisito.items() if not all(oks))
    print()
    print(f"Requisitos 1-40: "
          f"{sum(1 for n in range(1, 41) if n in por_requisito and all(por_requisito[n]))} "
          f"con resultado; sin verificación: {sin_verificar or 'ninguno'}; "
          f"con alguna falta: {con_falta or 'ninguno'}.")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--solo-postgres", action="store_true")
    p.add_argument("--cerrar-octubre", action="store_true")
    args = p.parse_args()
    print("Base:", q("SELECT current_database()")[0][0])

    if args.cerrar_octubre:
        from app.services.cierre_cuenta_service import cerrar_mes_todos
        r = cerrar_mes_todos(date(2026, 10, 1), hoy=date(2026, 11, 1))
        for c in r["cerrados"]:
            print(f"  CERRADO {c['cliente']}: {c['saldo_inicial']} + {c['total_facturas']} - "
                  f"{c['total_pagos']} = {c['saldo_final']}")
        for b in r["bloqueados"]:
            print(f"  BLOQUEADO {b['cliente']}: {b['motivo']}")

    verificar_postgres()
    verificar_sesiones_sensores_y_envios_postgres()
    if not args.solo_postgres:
        verificar_nosql()
        verificar_reportes()
        verificar_alertas_predicciones_y_lecturas()

    fallas = 0
    for numero, nombre, base, valor, ok in sorted(resultados):
        print(f"{'OK   ' if ok else 'FALTA'} #{numero:<3} {nombre:<45} [{base}] {valor}")
        fallas += not ok
    print(f"\n{len(resultados) - fallas} de {len(resultados)} verificaciones con resultado.")
    resumen_requisitos()
    return 1 if fallas else 0


if __name__ == "__main__":
    raise SystemExit(main())
