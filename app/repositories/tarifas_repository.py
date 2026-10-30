"""Persistencia PostgreSQL de cargas, reglas y snapshots tarifarios."""

import json

from app.database.postgres_connection import get_postgres_connection


def listar_envios_tarifables():
    with get_postgres_connection() as conn, conn.cursor() as cur:
        cur.execute("""SELECT id_envio, id_cliente, origen, destino, estado
                       FROM envio ORDER BY id_envio""")
        return cur.fetchall()


def listar_tipos_carga():
    with get_postgres_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT codigo, descripcion FROM tipo_carga WHERE activo ORDER BY codigo")
        return cur.fetchall()


def listar_tipos_transporte():
    with get_postgres_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT DISTINCT tipo FROM vehiculo ORDER BY tipo")
        return [row[0] for row in cur.fetchall()]


def crear_tipo_carga(codigo, descripcion):
    with get_postgres_connection() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO tipo_carga (codigo, descripcion) VALUES (%s, %s)",
                    (codigo, descripcion))


def agregar_carga(id_envio, tipo_carga, peso_kg, fragil, descripcion=None):
    with get_postgres_connection() as conn, conn.cursor() as cur:
        cur.execute("""INSERT INTO envio_carga
                       (id_envio, tipo_carga, peso_kg, fragil, descripcion)
                       VALUES (%s, %s, %s, %s, %s) RETURNING id_envio_carga""",
                    (id_envio, tipo_carga, peso_kg, fragil, descripcion))
        return cur.fetchone()[0]


def listar_cargas_envio(id_envio):
    with get_postgres_connection() as conn, conn.cursor() as cur:
        cur.execute("""SELECT ec.id_envio_carga, ec.tipo_carga, tc.descripcion,
                              ec.peso_kg, ec.fragil, ec.descripcion
                       FROM envio_carga ec JOIN tipo_carga tc USING (tipo_carga)
                       WHERE ec.id_envio = %s ORDER BY ec.id_envio_carga""", (id_envio,))
        return cur.fetchall()


def listar_tramos_tarifa(id_envio):
    with get_postgres_connection() as conn, conn.cursor() as cur:
        cur.execute("""SELECT id_tramo, medio_transporte, origen, destino, distancia_km
                       FROM tramo WHERE id_envio = %s
                       ORDER BY fecha_salida, id_tramo""", (id_envio,))
        return cur.fetchall()


def actualizar_distancia_tramo(id_tramo, distancia_km):
    with get_postgres_connection() as conn, conn.cursor() as cur:
        cur.execute("UPDATE tramo SET distancia_km = %s WHERE id_tramo = %s",
                    (distancia_km, id_tramo))
        return cur.rowcount == 1


def listar_tramos_envio(id_envio):
    with get_postgres_connection() as conn, conn.cursor() as cur:
        cur.execute("""SELECT id_tramo, medio_transporte, origen, destino, distancia_km
                       FROM tramo WHERE id_envio = %s ORDER BY fecha_salida, id_tramo""",
                    (id_envio,))
        return cur.fetchall()


def listar_reglas():
    with get_postgres_connection() as conn, conn.cursor() as cur:
        cur.execute("""SELECT id_regla, codigo, version, moneda, vigente_desde,
                              vigente_hasta, estado
                       FROM regla_tarifaria_version ORDER BY codigo, version DESC""")
        return cur.fetchall()


def crear_regla(codigo, version, moneda, vigente_desde, vigente_hasta,
                creada_por, componentes):
    with get_postgres_connection() as conn, conn.cursor() as cur:
        cur.execute("""INSERT INTO regla_tarifaria_version
                       (codigo, version, moneda, vigente_desde, vigente_hasta, creada_por)
                       VALUES (%s, %s, %s, %s, %s, %s) RETURNING id_regla""",
                    (codigo, version, moneda, vigente_desde, vigente_hasta, creada_por))
        id_regla = cur.fetchone()[0]
        for component in componentes:
            cur.execute("""INSERT INTO regla_tarifaria_componente
                           (id_regla, criterio, selector, ambito, base_calculo, importe)
                           VALUES (%s, %s, %s, %s, %s, %s)""",
                        (id_regla, component["criterio"], component.get("selector"),
                         component["ambito"], component["base_calculo"], component["importe"]))
        return id_regla


def obtener_regla(id_regla):
    with get_postgres_connection() as conn, conn.cursor() as cur:
        cur.execute("""SELECT id_regla, codigo, version, moneda, vigente_desde,
                              vigente_hasta, estado
                       FROM regla_tarifaria_version WHERE id_regla = %s""", (id_regla,))
        row = cur.fetchone()
        if row is None:
            return None
        cur.execute("""SELECT id_componente, criterio, selector, ambito,
                              base_calculo, importe
                       FROM regla_tarifaria_componente WHERE id_regla = %s
                       ORDER BY id_componente""", (id_regla,))
        return {
            "id_regla": row[0], "codigo": row[1], "version": row[2],
            "moneda": row[3], "vigente_desde": row[4], "vigente_hasta": row[5],
            "estado": row[6],
            "componentes": [dict(zip(
                ("id_componente", "criterio", "selector", "ambito", "base_calculo", "importe"), x
            )) for x in cur.fetchall()],
        }


def aprobar_regla(id_regla, usuario_id, referencia):
    with get_postgres_connection() as conn, conn.cursor() as cur:
        cur.execute("""SELECT codigo, estado FROM regla_tarifaria_version
                       WHERE id_regla = %s FOR UPDATE""", (id_regla,))
        row = cur.fetchone()
        if row is None or row[1] != "BORRADOR":
            raise ValueError("La regla no existe o ya no está en borrador.")
        cur.execute("""SELECT COUNT(*) FROM regla_tarifaria_componente
                       WHERE id_regla = %s AND criterio = 'BASE'
                         AND ambito = 'ENVIO' AND base_calculo = 'FIJO'
                         AND selector IS NULL""", (id_regla,))
        if cur.fetchone()[0] != 1:
            raise ValueError("La regla debe tener exactamente un componente base fijo por envío.")
        cur.execute("""SELECT id_regla FROM regla_tarifaria_version
                       WHERE codigo = %s AND estado = 'APROBADA' FOR UPDATE""", (row[0],))
        previous = cur.fetchone()
        if previous:
            cur.execute("""INSERT INTO regla_tarifaria_auditoria
                           (id_regla, estado_anterior, estado_nuevo, motivo,
                            usuario_id, id_transaccion)
                           VALUES (%s, 'APROBADA', 'REEMPLAZADA', %s, %s, txid_current())""",
                        (previous[0], f"Reemplazada por versión {id_regla}", usuario_id))
            cur.execute("""UPDATE regla_tarifaria_version SET estado = 'REEMPLAZADA'
                           WHERE id_regla = %s""", (previous[0],))
        cur.execute("""INSERT INTO regla_tarifaria_auditoria
                       (id_regla, estado_anterior, estado_nuevo, motivo,
                        usuario_id, id_transaccion)
                       VALUES (%s, 'BORRADOR', 'APROBADA', %s, %s, txid_current())""",
                    (id_regla, referencia, usuario_id))
        cur.execute("""UPDATE regla_tarifaria_version
                       SET estado = 'APROBADA', referencia_aprobacion = %s,
                           aprobado_por = %s, aprobado_en = CURRENT_TIMESTAMP
                       WHERE id_regla = %s""", (referencia, usuario_id, id_regla))


def obtener_datos_calculo(id_envio, id_regla):
    with get_postgres_connection() as conn, conn.cursor() as cur:
        cur.execute("""SELECT id_envio, estado FROM envio WHERE id_envio = %s""", (id_envio,))
        envio = cur.fetchone()
        if envio is None:
            raise ValueError("El envío no existe.")
        cur.execute("""SELECT codigo, version, moneda, vigente_desde, vigente_hasta, estado
                       FROM regla_tarifaria_version WHERE id_regla = %s""", (id_regla,))
        regla = cur.fetchone()
        if regla is None or regla[5] != "APROBADA":
            raise ValueError("La versión de regla no está aprobada.")
        cur.execute("""SELECT id_componente, criterio, selector, ambito,
                              base_calculo, importe
                       FROM regla_tarifaria_componente WHERE id_regla = %s
                       ORDER BY id_componente""", (id_regla,))
        componentes = [dict(zip(("id_componente", "criterio", "selector", "ambito",
                                  "base_calculo", "importe"), x)) for x in cur.fetchall()]
        cur.execute("""SELECT ec.id_envio_carga, ec.tipo_carga, ec.peso_kg, ec.fragil
                       FROM envio_carga ec WHERE ec.id_envio = %s
                       ORDER BY ec.id_envio_carga""", (id_envio,))
        cargas = [dict(zip(("id_envio_carga", "tipo_carga", "peso_kg", "fragil"), x))
                  for x in cur.fetchall()]
        cur.execute("""SELECT id_tramo, medio_transporte, distancia_km
                       FROM tramo WHERE id_envio = %s ORDER BY fecha_salida, id_tramo""", (id_envio,))
        tramos = [dict(zip(("id_tramo", "medio_transporte", "distancia_km"), x))
                  for x in cur.fetchall()]
        return {
            "envio": {"id_envio": envio[0], "estado": envio[1]},
            "regla": {"id_regla": id_regla, "codigo": regla[0], "version": regla[1],
                      "moneda": regla[2], "vigente_desde": regla[3],
                      "vigente_hasta": regla[4], "estado": regla[5]},
            "componentes": componentes, "cargas": cargas, "tramos": tramos,
        }


def guardar_tarifa_borrador(id_envio, regla, calculo, usuario_id):
    with get_postgres_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT id_envio FROM envio WHERE id_envio = %s FOR UPDATE", (id_envio,))
        if cur.fetchone() is None:
            raise ValueError("El envío no existe.")
        cur.execute("SELECT COALESCE(MAX(version), 0) + 1 FROM tarifa_envio WHERE id_envio = %s",
                    (id_envio,))
        version = cur.fetchone()[0]
        snapshot = {
            "regla": {"id_regla": regla["id_regla"], "codigo": regla["codigo"],
                      "version": regla["version"], "moneda": regla["moneda"]},
            "entradas": calculo["entradas"], "componentes": calculo["detalle"],
        }
        cur.execute("""INSERT INTO tarifa_envio
                       (id_envio, version, importe_base, importe_impuestos,
                        importe_total, moneda, id_configuracion_fiscal,
                        tratamiento_impositivo, estado, id_regla, detalle_calculo)
                       VALUES (%s, %s, %s, NULL, NULL, NULL, NULL, NULL,
                               'BORRADOR', %s, %s::jsonb) RETURNING id_tarifa""",
                    (id_envio, version, calculo["importe_base"], regla["id_regla"],
                     json.dumps(snapshot, default=str)))
        id_tarifa = cur.fetchone()[0]
        cur.execute("""INSERT INTO tarifa_envio_auditoria
                       (id_tarifa, estado_anterior, estado_nuevo, motivo, usuario_id)
                       VALUES (%s, NULL, 'BORRADOR', %s, %s)""",
                    (id_tarifa, "Cálculo de precio comercial guardado como borrador", usuario_id))
        return id_tarifa, version, snapshot


def obtener_tarifa(id_tarifa):
    with get_postgres_connection() as conn, conn.cursor() as cur:
        cur.execute("""SELECT id_tarifa, id_envio, version, importe_base,
                              importe_impuestos, importe_total, moneda, estado,
                              id_regla, detalle_calculo, referencia_aprobacion
                       FROM tarifa_envio WHERE id_tarifa = %s""", (id_tarifa,))
        row = cur.fetchone()
        if row is None:
            return None
        return dict(zip(("id_tarifa", "id_envio", "version", "importe_base",
                         "importe_impuestos", "importe_total", "moneda", "estado",
                         "id_regla", "detalle_calculo", "referencia_aprobacion"), row))


def listar_configuraciones_fiscales():
    with get_postgres_connection() as conn, conn.cursor() as cur:
        cur.execute("""SELECT id_configuracion_fiscal, codigo, version, tratamiento,
                              tasa, vigente_desde, vigente_hasta, referencia_aprobacion,
                              aprobado_por, aprobado_en, activa
                       FROM configuracion_fiscal WHERE activa ORDER BY codigo, version DESC""")
        return cur.fetchall()


def cargar_borrador_tarifa(id_tarifa):
    with get_postgres_connection() as conn, conn.cursor() as cur:
        cur.execute("""SELECT t.id_tarifa, t.id_envio, t.version, t.importe_base,
                              t.moneda, t.id_regla, t.detalle_calculo, t.estado,
                              cc.moneda
                       FROM tarifa_envio t JOIN envio e USING (id_envio)
                       LEFT JOIN cuenta_corriente cc ON cc.id_cliente = e.id_cliente
                       WHERE t.id_tarifa = %s""", (id_tarifa,))
        row = cur.fetchone()
        if row is None:
            return None
        return dict(zip(("id_tarifa", "id_envio", "version", "importe_base",
                         "moneda_tarifa", "id_regla", "detalle_calculo", "estado",
                         "moneda_cuenta"), row))


def aprobar_tarifa(id_tarifa, valores, usuario_id, referencia):
    with get_postgres_connection() as conn, conn.cursor() as cur:
        cur.execute("""SELECT t.id_envio, t.importe_base, t.estado, e.id_cliente
                       FROM tarifa_envio t JOIN envio e USING (id_envio)
                       WHERE t.id_tarifa = %s FOR UPDATE OF t, e""", (id_tarifa,))
        row = cur.fetchone()
        if row is None or row[2] != "BORRADOR":
            raise ValueError("La tarifa no existe o no está en borrador.")
        cur.execute("""SELECT moneda FROM cuenta_corriente
                       WHERE id_cliente = %s FOR UPDATE""", (row[3],))
        cuenta = cur.fetchone()
        if cuenta is None or not cuenta[0]:
            raise ValueError("La cuenta corriente no tiene una moneda configurada.")
        if str(valores["moneda"]).upper() != str(cuenta[0]).upper():
            raise ValueError("La moneda fiscal seleccionada no coincide con la cuenta.")
        cur.execute("""SELECT 1 FROM factura WHERE id_tarifa = %s LIMIT 1""", (id_tarifa,))
        if cur.fetchone():
            raise ValueError("La tarifa ya está referenciada por una factura.")
        cur.execute("""SELECT id_tarifa FROM tarifa_envio
                       WHERE id_envio = %s AND estado = 'APROBADA'
                       FOR UPDATE""", (row[0],))
        if cur.fetchone():
            raise ValueError(
                "El envío ya tiene una tarifa aprobada. No se modifica ni reemplaza en este flujo."
            )
        cur.execute("""INSERT INTO tarifa_envio_auditoria
                       (id_tarifa, estado_anterior, estado_nuevo, motivo,
                        usuario_id, id_transaccion)
                       VALUES (%s, 'BORRADOR', 'APROBADA', %s, %s, txid_current())""",
                    (id_tarifa, referencia, usuario_id))
        cur.execute("""UPDATE tarifa_envio
                       SET importe_impuestos = %s, importe_total = %s, moneda = %s,
                           id_configuracion_fiscal = %s,
                           tratamiento_impositivo = %s, tasa_impositiva = %s,
                           estado = 'APROBADA', referencia_aprobacion = %s,
                           aprobado_por = %s, aprobado_en = CURRENT_TIMESTAMP
                       WHERE id_tarifa = %s""",
                    (valores["importe_impuestos"], valores["importe_total"],
                     valores["moneda"], valores["id_configuracion_fiscal"],
                     valores["tratamiento_impositivo"], valores["tasa_impositiva"],
                     referencia, usuario_id, id_tarifa))


def reemplazar_tarifa_aprobada(id_tarifa, usuario_id, motivo):
    """Cambia solo el estado; el trigger valida el audit trail y referencias."""
    motivo = str(motivo or "").strip()
    if not motivo or not usuario_id:
        raise ValueError("El reemplazo requiere usuario y motivo documentado.")
    with get_postgres_connection() as conn, conn.cursor() as cur:
        cur.execute("""SELECT estado FROM tarifa_envio
                       WHERE id_tarifa = %s FOR UPDATE""", (id_tarifa,))
        row = cur.fetchone()
        if row is None or row[0] != "APROBADA":
            raise ValueError("Solo se puede reemplazar una tarifa aprobada.")
        cur.execute("""INSERT INTO tarifa_envio_auditoria
                       (id_tarifa, estado_anterior, estado_nuevo, motivo,
                        usuario_id, id_transaccion)
                       VALUES (%s, 'APROBADA', 'REEMPLAZADA', %s, %s, txid_current())""",
                    (id_tarifa, motivo, usuario_id))
        cur.execute("""UPDATE tarifa_envio SET estado = 'REEMPLAZADA'
                       WHERE id_tarifa = %s""", (id_tarifa,))

