"""Verifica, punto por punto de ANALISIS_PROMOCION.md, qué da resultado.

Solo lectura salvo con --cerrar-octubre (que cierra el período 2026-10 con
fecha simulada 01/11; usar solo en una copia de ensayo).

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


def punto(numero, nombre, valor, ok, base="PG"):
    resultados.append((numero, nombre, base, valor, ok))


def verificar_postgres():
    n = lambda sql, p=(): q(sql, p)[0][0]  # noqa: E731
    punto(1, "ABM Clientes", f"{n('SELECT count(*) FROM cliente')} clientes, "
          f"{n('SELECT count(DISTINCT pais) FROM cliente')} países",
          n("SELECT count(DISTINCT pais) FROM cliente") >= 3)
    partes = q("""SELECT count(*) FILTER (WHERE id_cliente IS NOT NULL),
                         count(*) FILTER (WHERE id_proveedor IS NOT NULL),
                         count(*) FILTER (WHERE id_operador IS NOT NULL),
                         count(*) FILTER (WHERE num_nonnulls(id_cliente, id_proveedor, id_operador) = 0)
                  FROM usuario""")[0]
    punto(2, "ABM Usuarios y Roles", f"usuarios cliente/proveedor/operador/internos = {partes}",
          all(x > 0 for x in partes))
    punto(4, "ABM Proveedores", f"{n('SELECT count(*) FROM proveedor')} proveedores",
          n("SELECT count(*) FROM proveedor") >= 2)
    punto(5, "ABM Operadores", f"{n('SELECT count(*) FROM operador_logistico')} operadores, "
          f"{n('SELECT count(*) FROM tramo WHERE id_operador IS NOT NULL')} tramos con operador",
          n("SELECT count(*) FROM operador_logistico") >= 2)
    punto(6, "Envíos -> contenedores -> sensores",
          f"{n('SELECT count(*) FROM envio_contenedor')} asociaciones, "
          f"{n('SELECT count(*) FROM sensor_iot')} sensores",
          n("SELECT count(*) FROM envio_contenedor") >= 10)
    tarifas = n("SELECT count(*) FROM regla_tarifaria_version WHERE estado = 'APROBADA'")
    punto(9, "Reglas (tarifa estándar)", f"{tarifas} regla aprobada", tarifas >= 1)
    por_envio = q("""SELECT count(*) FILTER (WHERE origen_emision = 'ENVIO_AUTOMATICA'),
                            count(*) FILTER (WHERE origen_emision = 'ENVIO_MANUAL')
                     FROM factura WHERE id_envio IS NOT NULL""")[0]
    punto(10, "Facturación y cobros (clientes)", f"facturas por envío automáticas/manuales = {por_envio}",
          por_envio[0] > 0 and por_envio[1] > 0)
    punto(12, "Facturación automática", f"{por_envio[0]} automáticas", por_envio[0] > 0)
    pagos = q("""SELECT count(*) FILTER (WHERE estado = 'Pagada'), count(*) FILTER (WHERE estado = 'Parcial'),
                        count(*) FILTER (WHERE estado = 'Pendiente') FROM factura WHERE id_envio IS NOT NULL""")[0]
    punto(13, "Registro de pagos", f"facturas por envío pagadas/parciales/pendientes = {pagos}",
          pagos[0] > 0 and pagos[1] > 0)
    concilia = n("""SELECT count(*) FROM cuenta_corriente cc
                    JOIN apertura_cuenta_corriente a USING (id_cliente)
                    WHERE cc.saldo <> a.saldo_inicial + (
                        SELECT COALESCE(sum(importe_firmado), 0) FROM movimiento_cuenta_corriente m
                        WHERE m.id_cliente = cc.id_cliente AND m.fecha_contable >= a.fecha_vigencia)""")
    punto(14, "Gestión de cuentas corrientes",
          f"{n('SELECT count(*) FROM cuenta_corriente')} cuentas; no concilian: {concilia}", concilia == 0)
    cierres = n("SELECT count(*) FROM cierre_cuenta_corriente WHERE periodo = DATE '2026-10-01'")
    aperturas = n("SELECT count(*) FROM apertura_cuenta_corriente")
    punto(15, "Cierre mensual", f"{aperturas} aperturas; cierres de 10/2026: {cierres}",
          aperturas == n("SELECT count(*) FROM cuenta_corriente"))
    terceros = q("""SELECT count(*) FILTER (WHERE id_operador IS NOT NULL), count(*) FILTER (WHERE id_proveedor IS NOT NULL),
                           count(*) FILTER (WHERE estado IN ('Pendiente','Parcial') AND fecha_vencimiento < CURRENT_DATE)
                    FROM factura_recibida""")[0]
    punto(16, "CC proveedores y operadores",
          f"facturas operador/proveedor = {terceros[:2]}, vencidas impagas = {terceros[2]}",
          terceros[0] > 0 and terceros[1] > 0 and terceros[2] > 0)
    entregados = q("""SELECT count(*), count(*) FILTER (WHERE fecha_entrega > (SELECT max(t.fecha_estimada_llegada)
                      FROM tramo t WHERE t.id_envio = e.id_envio)) FROM envio e WHERE estado = 'Entregado'""")[0]
    punto(24, "Trayectos / seguimiento", f"{entregados[0]} entregados con fecha real, {entregados[1]} tarde",
          entregados[0] >= 5 and entregados[1] >= 1)
    demorados = n("""SELECT count(*) FROM (SELECT e.id_envio FROM envio e JOIN tramo t USING (id_envio)
                     WHERE lower(e.estado) NOT IN ('entregado','cancelado')
                     GROUP BY e.id_envio HAVING max(t.fecha_estimada_llegada) < now()) x""")
    punto(35, "Reporte de envíos demorados (consulta existente)", f"{demorados} demorado(s)", demorados >= 1)
    incid = q("""SELECT count(*), count(*) FILTER (WHERE i.estado = 'Abierto'),
                        count(DISTINCT e.origen || '->' || e.destino)
                 FROM incidente i JOIN envio e USING (id_envio)""")[0]
    punto(25, "Incidentes", f"total/abiertos/rutas con incidentes = {incid}", incid[1] >= 1)
    punto(27, "Datos para ranking de rutas con incidentes",
          f"{incid[2]} rutas con incidentes (falta el reporte: día 3)", incid[2] >= 2)
    paises = n("SELECT count(DISTINCT c.pais) FROM envio e JOIN cliente c USING (id_cliente)")
    punto(28, "Ranking de clientes (consulta existente)", f"envíos de {paises} países", paises >= 3)
    medios = q("""SELECT medio_transporte, sum(importe) FROM factura_detalle
                  WHERE concepto = 'TRAMO' GROUP BY 1 ORDER BY 1""")
    punto(39, "Datos para costos por tipo de transporte", str(medios), len(medios) == 3)


def verificar_nosql():
    from pymongo import MongoClient  # noqa: F401  (conexión vía la app)
    from app.database.mongo_connection import get_mongo_database
    from app.repositories.lectura_iot_repository import abrir_conexion, cerrar_conexion
    from app.database.neo4j_connection import abrir_sesion_neo4j

    db = get_mongo_database()
    ev = db.eventos_logisticos.count_documents({})
    entregados = db.eventos_logisticos.count_documents({"tipo": "ENTREGADO"})
    punto(17, "Monitoreo: eventos", f"{ev} eventos ({entregados} ENTREGADO)", entregados >= 8, "Mongo")
    alertas = list(db.alertas.aggregate([{"$group": {"_id": "$tipo", "n": {"$sum": 1}}}]))
    tipos = {a["_id"]: a["n"] for a in alertas}
    punto(23, "Alertas de estado de sensores", str(tipos),
          any("transmisi" in str(k) or "lecturas" in str(k) for k in tipos), "Mongo")
    punto(32, "Anomalías de temperatura", f"Temperatura alta: {tipos.get('Temperatura alta', 0)}",
          tipos.get("Temperatura alta", 0) >= 1, "Mongo")
    punto(40, "Mensajería con las partes",
          f"{db.mensajes.count_documents({})} mensajes, {db.grupos_trabajo.count_documents({})} grupos",
          db.mensajes.count_documents({}) >= 6, "Mongo")
    punto(29, "Predicción de atrasos", f"{db.predicciones_riesgo.count_documents({})} predicciones",
          db.predicciones_riesgo.count_documents({}) > 0, "Mongo")

    cluster, s = abrir_conexion()
    try:
        meses = sorted({r.anio_mes for r in s.execute("SELECT DISTINCT contenedor_id, anio_mes FROM lecturas_por_contenedor")})
        gps = sum(1 for r in s.execute("SELECT gps_latitud FROM lecturas_por_contenedor") if r.gps_latitud is not None)
    finally:
        cerrar_conexion(cluster, s)
    punto(18, "Registro continuo de lecturas IoT", f"particiones por mes: {meses}", len(meses) >= 3, "Cassandra")
    punto(21, "Posiciones GPS", f"{gps} lecturas con GPS", gps > 50, "Cassandra")

    with abrir_sesion_neo4j() as ses:
        rp = ses.run("MATCH ()-[r:REALIZADO_POR]->(:Operador) RETURN count(r) AS c").single()["c"]
        env = ses.run("MATCH (e:Envio) RETURN count(e) AS c").single()["c"]
    pg_env = q("SELECT count(*) FROM envio")[0][0]
    punto(30, "Red clientes-operadores-envíos", f"{env}/{pg_env} envíos en el grafo, {rp} REALIZADO_POR",
          env == pg_env and rp > 0, "Neo4j")


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
    if not args.solo_postgres:
        verificar_nosql()

    fallas = 0
    for numero, nombre, base, valor, ok in sorted(resultados):
        print(f"{'OK   ' if ok else 'FALTA'} #{numero:<3} {nombre:<45} [{base}] {valor}")
        fallas += not ok
    print(f"\n{len(resultados) - fallas} de {len(resultados)} verificaciones con resultado.")
    return 1 if fallas else 0


if __name__ == "__main__":
    raise SystemExit(main())
