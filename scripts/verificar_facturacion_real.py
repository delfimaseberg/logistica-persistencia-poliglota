"""Verificación real (contra PostgreSQL) de la facturación por envío y pagos.

ESCRIBE DATOS: emite facturas y registra pagos de prueba. Ejecutar solo sobre
una base descartable (por ejemplo, una copia de la base principal).

Requiere una tarifa estándar aprobada y al menos un envío Entregado sin
factura (idealmente dos, para la prueba de concurrencia).

Uso (PowerShell, desde la raíz del proyecto):
    $env:POSTGRES_DB = "logistica_poliglota_verif"
    python scripts\\verificar_facturacion_real.py

La base se toma de POSTGRES_DB; las variables de entorno de la sesión tienen
prioridad sobre el archivo .env.
"""
import sys
import threading
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database.postgres_connection import get_postgres_connection  # noqa: E402
from app.repositories import facturacion_repository as repo  # noqa: E402

BASES_PROHIBIDAS = {"logistica_poliglota"}

fallos = []


def check(nombre, condicion, detalle=""):
    print(("OK    " if condicion else "FALLA ") + nombre + (f"  [{detalle}]" if detalle else ""))
    if not condicion:
        fallos.append(nombre)


def q(sql, params=()):
    with get_postgres_connection() as c, c.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall() if cur.description else None


def conteos():
    return q("""SELECT (SELECT count(*) FROM factura), (SELECT count(*) FROM pago),
                       (SELECT count(*) FROM movimiento_cuenta_corriente),
                       (SELECT COALESCE(sum(saldo), 0) FROM cuenta_corriente)""")[0]


def espera_error(nombre, fn, texto):
    antes = conteos()
    try:
        fn()
        check(nombre, False, "no lanzó error")
    except Exception as e:  # noqa: BLE001
        check(nombre, texto.lower() in str(e).lower() and conteos() == antes,
              f"{type(e).__name__}: {e}")


base = q("SELECT current_database()")[0][0]
print(f"Base: {base}\n")
if base in BASES_PROHIBIDAS:
    sys.exit("Esta verificación escribe datos: usar una base descartable, no "
             f"'{base}'. Ver instrucciones al inicio del archivo.")

saldo_previo = dict(q("SELECT id_cliente, saldo FROM cuenta_corriente"))
facturas_previas = [r[0] for r in q("SELECT id_factura FROM factura")]
pagos_previos = [r[0] for r in q("SELECT id_pago FROM pago")]

facturables = repo.listar_envios_facturables()
if not facturables:
    sys.exit("No hay envíos Entregados sin factura (¿se cargaron los datos de "
             "ejemplo y se registró el evento ENTREGADO?).")

# 1. Cotización = factura emitida
id_envio = facturables[0][0]
cotizacion = repo.cotizar_envio(id_envio)
factura = repo.emitir_factura_envio(id_envio)
check("factura por envío: importe igual a la cotización",
      factura["total"] == cotizacion["total"], f"{factura['total']} / {cotizacion['total']}")
f = q("""SELECT total, importe_base, importe_impuestos, estado, moneda,
                origen_emision, id_envio
         FROM factura WHERE id_factura = %s""", (factura["id_factura"],))[0]
check("factura por envío: Pendiente, ENVIO_MANUAL, ARS, total = neto + IVA",
      f[3] == "Pendiente" and f[4] == "ARS" and f[5] == "ENVIO_MANUAL"
      and f[6] == id_envio and f[0] == f[1] + f[2], str(f))
detalle = q("SELECT COALESCE(sum(importe), 0) FROM factura_detalle WHERE id_factura = %s",
            (factura["id_factura"],))[0][0]
check("detalle suma el neto", detalle == f[1], f"{detalle} / {f[1]}")
m = q("""SELECT importe_firmado FROM movimiento_cuenta_corriente
         WHERE tipo_origen = 'FACTURA' AND referencia_origen = %s""",
      (str(factura["id_factura"]),))
check("un movimiento FACTURA por el total con IVA", m == [(f[0],)], str(m))
espera_error("no se factura dos veces el mismo envío",
             lambda: repo.emitir_factura_envio(id_envio), "ya tiene")

# 2. Pagos parcial y total
parcial = (f[0] / 2).quantize(Decimal("0.01"))
idp1, est1 = repo.registrar_pago(factura["id_factura"], parcial, "Transferencia")
idp2, est2 = repo.registrar_pago(factura["id_factura"], f[0] - parcial, "Efectivo")
check("pagos: Parcial y luego Pagada", (est1, est2) == ("Parcial", "Pagada"))
espera_error("rechaza pago sobre factura pagada",
             lambda: repo.registrar_pago(factura["id_factura"], 1, "Efectivo"),
             "ya está pagada")
espera_error("rechaza pago que redondea a cero",
             lambda: repo.registrar_pago(factura["id_factura"], "0.001", "Efectivo"),
             "mayor a cero")

no_entregado = q("""SELECT id_envio FROM envio
                    WHERE LOWER(BTRIM(estado)) <> 'entregado' LIMIT 1""")
if no_entregado:
    espera_error("rechaza facturar un envío no entregado",
                 lambda: repo.emitir_factura_envio(no_entregado[0][0]),
                 "no está entregado")

# 3. Concurrencia: dos emisiones simultáneas del mismo envío
if len(facturables) > 1:
    id_envio_c = facturables[1][0]
    resultados, barrera = [], threading.Barrier(2)

    def emitir():
        barrera.wait()
        try:
            resultados.append(repo.emitir_factura_envio(id_envio_c))
        except Exception as e:  # noqa: BLE001
            resultados.append(e)

    hilos = [threading.Thread(target=emitir) for _ in range(2)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    check("concurrencia: una sola factura para el mismo envío",
          sum(not isinstance(r, Exception) for r in resultados) == 1
          and q("SELECT count(*) FROM factura WHERE id_envio = %s", (id_envio_c,))[0][0] == 1,
          "; ".join(str(r if isinstance(r, Exception) else r["id_factura"]) for r in resultados))
else:
    print("--    (un solo envío facturable; se omite la prueba de concurrencia)")

# 4. Invariantes
for cli, saldo, mov in q("""
        SELECT cc.id_cliente, cc.saldo, COALESCE(sum(m.importe_firmado), 0)
        FROM cuenta_corriente cc
        LEFT JOIN movimiento_cuenta_corriente m USING (id_cliente)
        GROUP BY cc.id_cliente, cc.saldo ORDER BY 1"""):
    previo = saldo_previo.get(cli, Decimal("0"))
    nuevos = q("""SELECT COALESCE(sum(importe_firmado), 0) FROM movimiento_cuenta_corriente
                  WHERE id_cliente = %s
                    AND NOT ((tipo_origen = 'FACTURA' AND referencia_origen::bigint = ANY(%s::bigint[]))
                          OR (tipo_origen = 'PAGO' AND referencia_origen::bigint = ANY(%s::bigint[])))""",
               (cli, facturas_previas, pagos_previos))[0][0]
    previos_mov = mov - nuevos
    check(f"cliente {cli}: saldo = saldo anterior + movimientos nuevos",
          saldo == previo + nuevos, f"{saldo} = {previo} + {nuevos} (previos en ledger {previos_mov})")

malas = q("""SELECT f.id_factura FROM factura f
             LEFT JOIN movimiento_cuenta_corriente m
               ON m.tipo_origen = 'FACTURA' AND m.tipo_movimiento = 'FACTURA'
              AND m.referencia_origen = f.id_factura::text
             WHERE NOT (f.id_factura = ANY(%s::bigint[]))
             GROUP BY f.id_factura, f.total
             HAVING count(m.*) <> 1 OR max(m.importe_firmado) <> f.total""",
          (facturas_previas,))
check("cada factura nueva tiene exactamente su movimiento", not malas, str(malas))
sin_origen = q("""SELECT count(*) FROM factura
                  WHERE NOT (id_factura = ANY(%s::bigint[]))
                    AND id_envio IS NULL AND id_reporte IS NULL""", (facturas_previas,))[0][0]
check("ninguna factura nueva sin envío ni reporte", sin_origen == 0, str(sin_origen))
check("ninguna factura quedó sobrepagada", not q("""
      SELECT f.id_factura FROM factura f JOIN pago p USING (id_factura)
      GROUP BY f.id_factura, f.total HAVING sum(p.monto) > f.total"""))

# 5. Reportes contra sumas directas
for fila in repo.reporte_facturacion_clientes():
    cli, _, cant, facturado, cobrado = fila[:5]
    esperado = q("""SELECT count(*), COALESCE(sum(total), 0) FROM factura
                    WHERE id_cliente = %s AND lower(trim(estado)) <> 'anulada'""", (cli,))[0]
    cob = q("""SELECT COALESCE(sum(p.monto), 0) FROM pago p JOIN factura f USING (id_factura)
               WHERE f.id_cliente = %s""", (cli,))[0][0]
    check(f"reporte cliente {cli}: totales sin duplicar",
          (cant, facturado, cobrado) == (esperado[0], esperado[1], cob))
    check(f"reporte cliente {cli}: por envío + históricas <= facturado",
          fila[5] + fila[6] <= facturado)

print(f"\n{len(fallos)} fallas" + (f": {fallos}" if fallos else " — todo OK"))
sys.exit(1 if fallos else 0)
