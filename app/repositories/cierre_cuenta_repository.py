"""Acceso transaccional a datos y snapshots de cierre de cuenta corriente."""

from app.database.postgres_connection import get_postgres_connection


class CierreExistente(Exception):
    """Indica que ya existe un snapshot para el cliente y período."""


def ejecutar_cierre_atomico(id_cliente, periodo, calcular_snapshot):
    """Lee, calcula e inserta un cierre bajo bloqueo de la cuenta.

    ``calcular_snapshot`` es una función pura proporcionada por el servicio.
    La inserción y las lecturas pertenecen a una misma transacción. El saldo
    actual solo se bloquea y consulta; nunca se actualiza al cerrar.
    """
    try:
        with get_postgres_connection() as conexion:
            with conexion.cursor() as cursor:
                cursor.execute("""
                    SELECT saldo, moneda
                    FROM cuenta_corriente
                    WHERE id_cliente = %s
                    FOR UPDATE
                """, (id_cliente,))
                fila_cuenta = cursor.fetchone()
                cuenta = None if fila_cuenta is None else {
                    "saldo": fila_cuenta[0],
                    "moneda": fila_cuenta[1],
                }

                cursor.execute("""
                    SELECT id_cierre
                    FROM cierre_cuenta_corriente
                    WHERE id_cliente = %s AND periodo = %s
                    FOR UPDATE
                """, (id_cliente, periodo))
                existente = cursor.fetchone()
                if existente is not None:
                    raise CierreExistente(
                        f"Ya existe el cierre {existente[0]} para el período."
                    )

                cursor.execute("""
                    SELECT id_apertura, id_cliente, moneda, saldo_inicial,
                           fecha_vigencia, referencia_fuente,
                           aprobado_por, aprobado_en
                    FROM apertura_cuenta_corriente
                    WHERE id_cliente = %s
                """, (id_cliente,))
                fila_apertura = cursor.fetchone()
                apertura = None if fila_apertura is None else {
                    "id_apertura": fila_apertura[0],
                    "id_cliente": fila_apertura[1],
                    "moneda": fila_apertura[2],
                    "saldo_inicial": fila_apertura[3],
                    "fecha_vigencia": fila_apertura[4],
                    "referencia_fuente": fila_apertura[5],
                    "aprobado_por": fila_apertura[6],
                    "aprobado_en": fila_apertura[7],
                }

                cursor.execute("""
                    SELECT id_factura, fecha_emision, total, estado, moneda
                    FROM factura
                    WHERE id_cliente = %s
                    ORDER BY fecha_emision, id_factura
                """, (id_cliente,))
                facturas = [
                    {
                        "id_factura": fila[0],
                        "fecha_emision": fila[1],
                        "total": fila[2],
                        "estado": fila[3],
                        "moneda": fila[4],
                    }
                    for fila in cursor.fetchall()
                ]

                cursor.execute("""
                    SELECT p.id_pago, p.id_factura, p.fecha, p.monto,
                           f.moneda, f.estado
                    FROM pago p
                    JOIN factura f ON f.id_factura = p.id_factura
                    WHERE f.id_cliente = %s
                    ORDER BY p.fecha, p.id_pago
                """, (id_cliente,))
                pagos = [
                    {
                        "id_pago": fila[0],
                        "id_factura": fila[1],
                        "fecha": fila[2],
                        "monto": fila[3],
                        "moneda": fila[4],
                        "estado_factura": fila[5],
                    }
                    for fila in cursor.fetchall()
                ]

                cursor.execute("""
                    SELECT cc.id_correccion, cc.id_factura_original,
                           cc.tipo, cc.importe, cc.moneda,
                           cc.motivo, cc.referencia_aprobacion,
                           cc.aprobado_por, cc.aprobada_en,
                           cc.registrada_en, f.fecha_emision
                    FROM correccion_factura cc
                    JOIN factura f ON f.id_factura = cc.id_factura_original
                    WHERE f.id_cliente = %s
                    ORDER BY cc.registrada_en, cc.id_correccion
                """, (id_cliente,))
                correcciones = [
                    {
                        "id_correccion": fila[0],
                        "id_factura_original": fila[1],
                        "tipo": fila[2],
                        "importe": fila[3],
                        "moneda": fila[4],
                        "motivo": fila[5],
                        "referencia_aprobacion": fila[6],
                        "aprobado_por": fila[7],
                        "aprobada_en": fila[8],
                        "registrada_en": fila[9],
                        "fecha_emision_original": fila[10],
                    }
                    for fila in cursor.fetchall()
                ]

                cursor.execute("""
                    SELECT id_movimiento, moneda, tipo_movimiento,
                           importe_firmado, fecha_contable, periodo_origen,
                           tipo_origen, referencia_origen,
                           referencia_documental
                    FROM movimiento_cuenta_corriente
                    WHERE id_cliente = %s
                    ORDER BY fecha_contable, id_movimiento
                """, (id_cliente,))
                movimientos = [
                    {
                        "id_movimiento": fila[0],
                        "moneda": fila[1],
                        "tipo_movimiento": fila[2],
                        "importe_firmado": fila[3],
                        "fecha_contable": fila[4],
                        "periodo_origen": fila[5],
                        "tipo_origen": fila[6],
                        "referencia_origen": fila[7],
                        "referencia_documental": fila[8],
                    }
                    for fila in cursor.fetchall()
                ]

                cursor.execute("""
                    SELECT periodo
                    FROM cierre_cuenta_corriente
                    WHERE id_cliente = %s
                    ORDER BY periodo
                """, (id_cliente,))
                periodos_cerrados = [fila[0] for fila in cursor.fetchall()]

                datos = {
                    "cuenta": cuenta,
                    "apertura": apertura,
                    "facturas": facturas,
                    "pagos": pagos,
                    "correcciones": correcciones,
                    "movimientos": movimientos,
                    "periodos_cerrados": periodos_cerrados,
                }
                snapshot = calcular_snapshot(datos)

                cursor.execute("""
                    INSERT INTO cierre_cuenta_corriente (
                        id_cliente, periodo, moneda, saldo_inicial,
                        total_facturas, total_pagos, ajustes_netos,
                        saldo_final, referencia_saldo_inicial, id_apertura
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id_cierre
                """, (
                    id_cliente,
                    periodo,
                    snapshot["moneda"],
                    snapshot["saldo_inicial"],
                    snapshot["total_facturas"],
                    snapshot["total_pagos"],
                    snapshot["ajustes_netos"],
                    snapshot["saldo_final"],
                    snapshot["referencia_saldo_inicial"],
                    snapshot["id_apertura"],
                ))
                id_cierre = cursor.fetchone()[0]
                return {"id_cierre": id_cierre, **snapshot}
    except Exception as error:
        # La restricción única sigue siendo la última defensa ante carreras.
        if getattr(error, "sqlstate", None) == "23505":
            raise CierreExistente(
                "Ya existe un cierre para el cliente y período solicitados."
            ) from error
        raise
