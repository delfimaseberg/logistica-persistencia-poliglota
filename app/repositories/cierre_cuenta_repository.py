"""Acceso transaccional a datos y snapshots de cierre de cuenta corriente."""

from psycopg import errors

from app.database.postgres_connection import get_postgres_connection


ZONA_CONTABLE = "America/Argentina/Buenos_Aires"  # los días contables se cuentan en hora argentina


class CierreExistente(Exception):  # ya hay cierre de ese mes; el servicio lo convierte en CierreDuplicado
    """Indica que ya existe un snapshot para el cliente y período."""


def _leer_datos(cursor, id_cliente, bloquear):  # trae todo lo que necesita el cierre; la usan leer_datos_cierre y ejecutar_cierre_atomico
    """Cuenta, apertura, documentos, ledger y períodos cerrados del cliente.

    Con bloquear=True la cuenta queda tomada FOR UPDATE (cierre real).
    """
    cursor.execute(f"""
        SELECT saldo, moneda
        FROM cuenta_corriente
        WHERE id_cliente = %s
        {"FOR UPDATE" if bloquear else ""}
    """, (id_cliente,))
    fila_cuenta = cursor.fetchone()
    cuenta = None if fila_cuenta is None else {
        "saldo": fila_cuenta[0],
        "moneda": fila_cuenta[1],
    }

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
        JOIN factura f ON f.id_factura = p.id_factura  -- los pagos del cliente se buscan por sus facturas
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
               cc.aprobada_por, cc.aprobada_en,
               cc.registrada_en, f.fecha_emision
        FROM correccion_factura cc
        JOIN factura f ON f.id_factura = cc.id_factura_original  -- con la fecha de la factura corregida
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

    return {
        "cuenta": cuenta,
        "apertura": apertura,
        "facturas": facturas,
        "pagos": pagos,
        "correcciones": correcciones,
        "movimientos": movimientos,
        "periodos_cerrados": periodos_cerrados,
    }


def leer_datos_cierre(id_cliente):  # los mismos datos sin bloquear; la usa previsualizar_apertura
    """Mismos datos que usa el cierre, sin bloquear ni escribir."""
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            return _leer_datos(cursor, id_cliente, bloquear=False)


def ejecutar_cierre_atomico(id_cliente, periodo, calcular_snapshot):  # lee, calcula y guarda el cierre en una sola transacción; la usa cerrar_cuenta_mensual
    """Lee, calcula e inserta un cierre bajo bloqueo de la cuenta.

    ``calcular_snapshot`` es una función pura proporcionada por el servicio.
    La inserción y las lecturas pertenecen a una misma transacción. El saldo
    actual solo se bloquea y consulta; nunca se actualiza al cerrar.
    """
    try:
        with get_postgres_connection() as conexion:
            with conexion.cursor() as cursor:
                cursor.execute("""
                    SELECT 1 FROM cuenta_corriente
                    WHERE id_cliente = %s
                    FOR UPDATE  -- bloquea la cuenta: nadie factura ni paga mientras se cierra
                """, (id_cliente,))

                cursor.execute("""
                    SELECT id_cierre
                    FROM cierre_cuenta_corriente
                    WHERE id_cliente = %s AND periodo = %s
                    FOR UPDATE
                """, (id_cliente, periodo))
                existente = cursor.fetchone()
                if existente is not None:  # ese mes ya tiene cierre: no se cierra dos veces
                    raise CierreExistente(
                        f"Ya existe el cierre {existente[0]} para el período."
                    )

                datos = _leer_datos(cursor, id_cliente, bloquear=True)
                snapshot = calcular_snapshot(datos)  # el cálculo lo hace el servicio; si no concilia, no se guarda nada

                cursor.execute("""
                    INSERT INTO cierre_cuenta_corriente (
                        id_cliente, periodo, moneda, saldo_inicial,
                        total_facturas, total_pagos, ajustes_netos,
                        saldo_final, referencia_saldo_inicial, id_apertura
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id_cierre  -- el cierre guardado ya no se modifica
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
        if getattr(error, "sqlstate", None) == "23505":  # el índice único también impide dos cierres del mismo mes
            raise CierreExistente(
                "Ya existe un cierre para el cliente y período solicitados."
            ) from error
        raise


def listar_clientes_con_cuenta():  # clientes a cerrar; la usa cerrar_mes_todos
    """(id_cliente, razón social) de todos los clientes con cuenta corriente."""
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT c.id_cliente, c.razon_social
                FROM cuenta_corriente cc
                JOIN cliente c ON c.id_cliente = cc.id_cliente
                ORDER BY c.id_cliente
            """)
            return cursor.fetchall()


def listar_aperturas():  # aperturas registradas; las muestra la opción 10 de facturación
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT a.id_apertura, a.id_cliente, c.razon_social,
                       a.saldo_inicial, a.moneda, a.fecha_vigencia,
                       a.referencia_fuente, u.nombre || ' ' || u.apellido,
                       a.aprobado_en
                FROM apertura_cuenta_corriente a
                JOIN cliente c ON c.id_cliente = a.id_cliente
                JOIN usuario u ON u.id_usuario = a.aprobado_por
                ORDER BY a.id_cliente
            """)
            return cursor.fetchall()


def calcular_saldo_documentos(id_cliente, fecha_vigencia):  # saldo sugerido para la apertura; la usan la opción 10 de facturación y previsualizar_apertura
    """Saldo según facturas (no anuladas) y pagos anteriores a la fecha.

    Es el saldo sugerido para una apertura que rige desde fecha_vigencia:
    los documentos de esa fecha en adelante deben tener movimiento propio.
    """
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT
                    COALESCE((
                        SELECT SUM(total) FROM factura
                        WHERE id_cliente = %s
                          AND LOWER(TRIM(estado)) <> 'anulada'  -- las anuladas no son deuda
                          AND fecha_emision < %s
                    ), 0),
                    COALESCE((
                        SELECT SUM(p.monto) FROM pago p
                        JOIN factura f ON f.id_factura = p.id_factura
                        WHERE f.id_cliente = %s
                          AND (p.fecha AT TIME ZONE %s)::date < %s  -- pagos anteriores a la apertura, en hora argentina
                    ), 0)
            """, (id_cliente, fecha_vigencia, id_cliente, ZONA_CONTABLE,
                  fecha_vigencia))
            facturado, pagado = cursor.fetchone()
    return facturado, pagado, facturado - pagado  # saldo sugerido: facturado menos pagado


def registrar_apertura(id_cliente, saldo_inicial, fecha_vigencia, referencia,  # guarda la apertura del cliente (una sola); la usa registrar_apertura del servicio
                       aprobado_por):
    """Registra la apertura (una por cliente). El aprobador debe ser un
    usuario interno activo (sin cliente, proveedor ni operador)."""
    try:
        with get_postgres_connection() as conexion:
            with conexion.cursor() as cursor:
                cursor.execute("""
                    SELECT moneda FROM cuenta_corriente
                    WHERE id_cliente = %s
                    FOR UPDATE  -- bloquea la cuenta mientras se registra
                """, (id_cliente,))
                cuenta = cursor.fetchone()
                if cuenta is None:
                    raise ValueError("El cliente no tiene cuenta corriente.")
                if not cuenta[0]:
                    raise ValueError("La cuenta corriente no tiene moneda.")

                cursor.execute("""
                    SELECT u.estado, u.id_cliente, u.id_proveedor,
                           u.id_operador, r.nivel_permisos
                    FROM usuario u
                    JOIN rol r ON r.id_rol = u.id_rol
                    WHERE u.id_usuario = %s
                """, (aprobado_por,))
                aprobador = cursor.fetchone()
                if aprobador is None or aprobador[0] != "ACTIVO":
                    raise ValueError("El aprobador no existe o no está activo.")
                if any(parte is not None for parte in aprobador[1:4]):  # solo un usuario interno puede aprobar
                    raise ValueError(
                        "La apertura debe aprobarla un usuario interno "
                        "(sin cliente, proveedor ni operador)."
                    )

                cursor.execute("""
                    SELECT 1 FROM cierre_cuenta_corriente
                    WHERE id_cliente = %s LIMIT 1
                """, (id_cliente,))
                if cursor.fetchone() is not None:  # si ya hay meses cerrados, la apertura no se puede cambiar
                    raise ValueError(
                        "El cliente ya tiene cierres: la apertura no se puede cambiar."
                    )

                cursor.execute("""
                    INSERT INTO apertura_cuenta_corriente (
                        id_cliente, moneda, saldo_inicial, fecha_vigencia,
                        referencia_fuente, aprobado_por, aprobado_en
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    RETURNING id_apertura
                """, (id_cliente, cuenta[0], saldo_inicial, fecha_vigencia,
                      referencia, aprobado_por))
                return cursor.fetchone()[0]
    except errors.UniqueViolation:  # el índice único permite una sola apertura por cliente
        raise ValueError("El cliente ya tiene una apertura registrada.") from None
