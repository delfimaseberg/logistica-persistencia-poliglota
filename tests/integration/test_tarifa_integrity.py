"""Pruebas de triggers financieros; requieren 004, 007 y 008 en el stack aislado."""

import json
import os
from datetime import date, datetime, timezone
from uuid import uuid4

import psycopg
import pytest


class _RollbackIntegrationData(Exception):
    pass


def _assert_statement_blocked(connection, statement, params=()):
    with pytest.raises(psycopg.Error):
        with connection.transaction():
            with connection.cursor() as cursor:
                cursor.execute(statement, params)


def _assert_transaction_blocked(connection, statements):
    with pytest.raises(psycopg.Error):
        with connection.transaction():
            with connection.cursor() as cursor:
                for statement, params in statements:
                    cursor.execute(statement, params)


def test_tarifa_y_reglas_aprobadas_conservan_snapshot_y_auditoria(integration_guard):
    connect_args = {
        "host": os.environ["POSTGRES_HOST"],
        "port": os.environ["POSTGRES_PORT"],
        "dbname": os.environ["POSTGRES_DB"],
        "user": os.environ["POSTGRES_USER"],
        "password": os.environ["POSTGRES_PASSWORD"],
    }

    with psycopg.connect(**connect_args) as connection:
        try:
            with connection.transaction():
                with connection.cursor() as cursor:
                    cursor.execute("""SELECT count(*) FROM pg_trigger
                                      WHERE NOT tgisinternal AND tgname IN
                                      ('trg_tarifa_envio_inmutable',
                                       'trg_regla_tarifaria_inmutable',
                                       'trg_regla_tarifaria_componente_inmutable')""")
                    if cursor.fetchone()[0] != 3:
                        pytest.skip("Aplicar 007 y 008 solo en la base PostgreSQL aislada antes del test.")

                    token = uuid4().hex[:12]
                    cursor.execute("""INSERT INTO cliente
                                      (razon_social, cuit, email, pais, estado)
                                      VALUES (%s, %s, %s, 'Argentina', 'Activo')
                                      RETURNING id_cliente""",
                                   (f"IT tarifa {token}", f"8{uuid4().int % 10**12:012d}",
                                    f"it-tarifa-{token}@invalid.test"))
                    client_id = cursor.fetchone()[0]
                    cursor.execute("""INSERT INTO rol (descripcion, nivel_permisos)
                                      VALUES (%s, 3) RETURNING id_rol""", (f"IT tarifa {token}",))
                    role_id = cursor.fetchone()[0]
                    cursor.execute("""INSERT INTO usuario
                                      (id_cliente, id_rol, nombre, apellido, email,
                                       contrasena_encriptada, estado)
                                      VALUES (%s, %s, 'IT', 'Tarifa', %s, 'test-hash', 'ACTIVO')
                                      RETURNING id_usuario""",
                                   (client_id, role_id, f"it-tarifa-user-{token}@invalid.test"))
                    user_id = cursor.fetchone()[0]

                    cursor.execute("""INSERT INTO configuracion_fiscal
                                      (codigo, version, descripcion, tratamiento, tasa,
                                       vigente_desde, referencia_aprobacion, aprobado_por,
                                       aprobado_en, activa)
                                      VALUES (%s, 1, 'solo integración', 'TEST', NULL,
                                              CURRENT_DATE, 'ref-test', %s, %s, TRUE)
                                      RETURNING id_configuracion_fiscal""",
                                   (f"IT_{token}", user_id, datetime.now(timezone.utc)))
                    fiscal_id = cursor.fetchone()[0]

                    cursor.execute("""INSERT INTO regla_tarifaria_version
                                      (codigo, version, moneda, vigente_desde, estado,
                                       creada_por)
                                      VALUES (%s, 1, 'TST', CURRENT_DATE, 'BORRADOR', %s)
                                      RETURNING id_regla""",
                                   (f"IT_{token}", user_id))
                    rule_id = cursor.fetchone()[0]
                    cursor.execute("""INSERT INTO regla_tarifaria_componente
                                      (id_regla, criterio, ambito, base_calculo, importe)
                                      VALUES (%s, 'BASE', 'ENVIO', 'FIJO', 10.00)""", (rule_id,))
                    cursor.execute("""INSERT INTO regla_tarifaria_auditoria
                                      (id_regla, estado_anterior, estado_nuevo, motivo,
                                       usuario_id, id_transaccion)
                                      VALUES (%s, 'BORRADOR', 'APROBADA', 'test', %s, txid_current())""",
                                   (rule_id, user_id))
                    cursor.execute("""UPDATE regla_tarifaria_version
                                      SET estado='APROBADA', referencia_aprobacion='ref-test',
                                          aprobado_por=%s, aprobado_en=%s
                                      WHERE id_regla=%s""",
                                   (user_id, datetime.now(timezone.utc), rule_id))

                    shipment_ids = []
                    for suffix in ("linked", "replaceable"):
                        cursor.execute("""INSERT INTO envio
                                          (id_cliente, origen, destino, estado, prioridad)
                                          VALUES (%s, %s, %s, 'Pendiente', 'Media')
                                          RETURNING id_envio""",
                                       (client_id, f"IT origen {suffix} {token}",
                                        f"IT destino {suffix} {token}"))
                        shipment_ids.append(cursor.fetchone()[0])

                    tariff_ids = []
                    snapshot = {"regla": {"id_regla": rule_id, "version": 1},
                                "componentes": [{"importe": "10.00"}]}
                    for shipment_id in shipment_ids:
                        cursor.execute("""INSERT INTO tarifa_envio
                                          (id_envio, version, importe_base, importe_impuestos,
                                           importe_total, moneda, id_configuracion_fiscal,
                                           tratamiento_impositivo, estado, referencia_aprobacion,
                                           aprobado_por, aprobado_en, id_regla, detalle_calculo)
                                          VALUES (%s, 1, 10.00, 0.00, 10.00, 'TST', %s,
                                                  'TEST', 'BORRADOR', 'ref-test', %s, %s, %s, %s)
                                          RETURNING id_tarifa""",
                                       (shipment_id, fiscal_id, user_id,
                                        datetime.now(timezone.utc), rule_id,
                                        json.dumps(snapshot)))
                        tariff_ids.append(cursor.fetchone()[0])
                        cursor.execute("""INSERT INTO tarifa_envio_auditoria
                                          (id_tarifa, estado_anterior, estado_nuevo,
                                           motivo, usuario_id, id_transaccion)
                                          VALUES (%s, 'BORRADOR', 'APROBADA', 'test', %s, txid_current())""",
                                       (tariff_ids[-1], user_id))
                        cursor.execute("""UPDATE tarifa_envio SET estado='APROBADA'
                                          WHERE id_tarifa=%s""", (tariff_ids[-1],))

                    # Una factura sintética conserva la FK a la tarifa histórica.
                    cursor.execute("""INSERT INTO factura
                                      (id_cliente, fecha_emision, total, estado,
                                       id_envio, id_tarifa)
                                      VALUES (%s, CURRENT_DATE, 10.00, 'Pendiente', %s, %s)""",
                                   (client_id, shipment_ids[0], tariff_ids[0]))

                    # No se puede cambiar contenido ni borrar una tarifa aprobada.
                    _assert_statement_blocked(
                        connection,
                        "UPDATE tarifa_envio SET importe_total = 11.00 WHERE id_tarifa = %s",
                        (tariff_ids[0],),
                    )
                    _assert_statement_blocked(
                        connection,
                        "UPDATE tarifa_envio SET detalle_calculo = '{}'::jsonb WHERE id_tarifa = %s",
                        (tariff_ids[0],),
                    )
                    _assert_statement_blocked(
                        connection, "DELETE FROM tarifa_envio WHERE id_tarifa = %s",
                        (tariff_ids[0],),
                    )

                    # El reemplazo no procede si una factura ya referencia la tarifa.
                    _assert_transaction_blocked(connection, [
                        ("""INSERT INTO tarifa_envio_auditoria
                            (id_tarifa, estado_anterior, estado_nuevo, motivo,
                             usuario_id, id_transaccion)
                            VALUES (%s, 'APROBADA', 'REEMPLAZADA', 'test', %s, txid_current())""",
                         (tariff_ids[0], user_id)),
                        ("UPDATE tarifa_envio SET estado = 'REEMPLAZADA' WHERE id_tarifa = %s",
                         (tariff_ids[0],)),
                    ])

                    # Sin factura: reemplazo permitido solo con auditoría en la misma tx.
                    _assert_statement_blocked(
                        connection,
                        "UPDATE tarifa_envio SET estado = 'REEMPLAZADA' WHERE id_tarifa = %s",
                        (tariff_ids[1],),
                    )
                    cursor.execute("""INSERT INTO tarifa_envio_auditoria
                                      (id_tarifa, estado_anterior, estado_nuevo, motivo,
                                       usuario_id, id_transaccion)
                                      VALUES (%s, 'APROBADA', 'REEMPLAZADA', 'reemplazo de prueba',
                                              %s, txid_current())""",
                                   (tariff_ids[1], user_id))
                    cursor.execute("UPDATE tarifa_envio SET estado = 'REEMPLAZADA' WHERE id_tarifa = %s",
                                   (tariff_ids[1],))
                    cursor.execute("""SELECT estado, importe_total, detalle_calculo
                                      FROM tarifa_envio WHERE id_tarifa = %s""", (tariff_ids[1],))
                    state, total, detail = cursor.fetchone()
                    assert state == "REEMPLAZADA"
                    assert str(total) == "10.00"
                    assert detail == snapshot
                    cursor.execute("""SELECT count(*) FROM tarifa_envio_auditoria
                                      WHERE id_tarifa = %s AND estado_nuevo = 'REEMPLAZADA'
                                        AND id_transaccion = txid_current()""", (tariff_ids[1],))
                    assert cursor.fetchone()[0] == 1

                    # Las facturas mantienen su FK y las tarifas reemplazadas son inmutables.
                    cursor.execute("SELECT id_tarifa FROM factura WHERE id_tarifa = %s",
                                   (tariff_ids[0],))
                    assert cursor.fetchone()[0] == tariff_ids[0]
                    _assert_statement_blocked(
                        connection,
                        "UPDATE tarifa_envio SET importe_base = 12.00 WHERE id_tarifa = %s",
                        (tariff_ids[1],),
                    )

                    # Reglas aprobadas no se editan ni borran; borradores sí se editan.
                    _assert_statement_blocked(
                        connection, "DELETE FROM regla_tarifaria_version WHERE id_regla = %s",
                        (rule_id,),
                    )
                    _assert_statement_blocked(
                        connection, "UPDATE regla_tarifaria_version SET version = 2 WHERE id_regla = %s",
                        (rule_id,),
                    )
                    _assert_statement_blocked(
                        connection,
                        "DELETE FROM regla_tarifaria_componente WHERE id_regla = %s",
                        (rule_id,),
                    )

                    cursor.execute("""INSERT INTO regla_tarifaria_version
                                      (codigo, version, moneda, vigente_desde,
                                       estado, creada_por)
                                      VALUES (%s, 1, 'TST', CURRENT_DATE, 'BORRADOR', %s)
                                      RETURNING id_regla""", (f"DRAFT_{token}", user_id))
                    draft_id = cursor.fetchone()[0]
                    _assert_statement_blocked(
                        connection,
                        "UPDATE regla_tarifaria_componente SET id_regla = %s WHERE id_regla = %s",
                        (draft_id, rule_id),
                    )
                    cursor.execute("""INSERT INTO regla_tarifaria_componente
                                      (id_regla, criterio, ambito, base_calculo, importe)
                                      VALUES (%s, 'BASE', 'ENVIO', 'FIJO', 1.00)
                                      RETURNING id_componente""", (draft_id,))
                    component_id = cursor.fetchone()[0]
                    cursor.execute("UPDATE regla_tarifaria_componente SET importe = 2.00 WHERE id_componente = %s",
                                   (component_id,))
                    _assert_statement_blocked(
                        connection,
                        "UPDATE regla_tarifaria_componente SET id_regla = %s WHERE id_componente = %s",
                        (rule_id, component_id),
                    )
                    cursor.execute("UPDATE regla_tarifaria_version SET vigente_hasta = CURRENT_DATE WHERE id_regla = %s",
                                   (draft_id,))
                    cursor.execute("SELECT importe FROM regla_tarifaria_componente WHERE id_componente = %s",
                                   (component_id,))
                    assert cursor.fetchone()[0] == 2
                    _assert_statement_blocked(
                        connection, "DELETE FROM regla_tarifaria_version WHERE id_regla = %s",
                        (draft_id,),
                    )

                    raise _RollbackIntegrationData()
        except _RollbackIntegrationData:
            pass
