"""Cuenta corriente de proveedores y operadores logísticos (PostgreSQL).

Sentido inverso al del cliente: el saldo es lo que NOSOTROS les debemos.
- Factura recibida: suma (movimiento FACTURA_RECIBIDA positivo).
- Pago que les hacemos: resta (movimiento PAGO_EMITIDO negativo).

Mismo patrón que facturacion_repository: documento, saldo y movimiento en una
sola transacción, con bloqueos FOR UPDATE y sin pagos mayores a lo pendiente.
"""

from datetime import timedelta

from psycopg import errors

from app.database.postgres_connection import get_postgres_connection
from app.utils.validaciones_terceros import (
    MONEDA_TERCEROS,
    envio_entregado,
    hoy_contable,
    importe_positivo,
    validar_fechas_factura,
    validar_numero_comprobante,
    validar_origen_factura,
    validar_tipo_titular,
)


ZONA_CONTABLE = "America/Argentina/Buenos_Aires"

# Nombres fijos (nunca vienen del usuario): seguros para interpolar.
_TITULARES = {
    "PROVEEDOR": ("proveedor", "id_proveedor"),
    "OPERADOR": ("operador_logistico", "id_operador"),
}


def _titular(tipo_titular):
    tipo = validar_tipo_titular(tipo_titular)
    tabla, columna = _TITULARES[tipo]
    return tipo, tabla, columna


def _bloquear_o_crear_cuenta(cursor, columna, id_titular):
    """Bloquea la cuenta del titular; si no existe la crea en ARS con saldo 0."""
    cursor.execute(f"""
        SELECT id_cuenta_tercero, moneda
        FROM cuenta_corriente_tercero
        WHERE {columna} = %s
        FOR UPDATE
    """, (id_titular,))
    cuenta = cursor.fetchone()
    if cuenta is not None:
        return cuenta

    cursor.execute(f"""
        INSERT INTO cuenta_corriente_tercero ({columna}, saldo, moneda)
        VALUES (%s, 0, %s)
        RETURNING id_cuenta_tercero, moneda
    """, (id_titular, MONEDA_TERCEROS))
    return cursor.fetchone()


def registrar_factura_recibida(
    tipo_titular,
    id_titular,
    numero_comprobante,
    total,
    fecha_emision,
    fecha_vencimiento=None,
    id_tramo=None,
    concepto=None,
    registrado_por=None,
    hoy=None,
):
    """Registra una factura que nos emite un proveedor u operador.

    Operador: debe indicar el tramo que realizó; el envío del tramo tiene que
    estar Entregado (el transportista factura una vez hecho el trabajo) y el
    tramo no puede tener otra factura vigente.
    Proveedor: sin tramo y con concepto.
    Vencimiento por defecto: 30 días desde la emisión.
    """
    tipo, tabla, columna = _titular(tipo_titular)
    total = importe_positivo(total, "El importe debe ser mayor a cero.")
    numero = validar_numero_comprobante(numero_comprobante)
    fecha_emision, fecha_vencimiento = validar_fechas_factura(
        fecha_emision, fecha_vencimiento, hoy=hoy
    )
    id_tramo, concepto = validar_origen_factura(tipo, id_tramo, concepto)

    try:
        with get_postgres_connection() as conexion:
            with conexion.cursor() as cursor:
                cursor.execute(f"""
                    SELECT estado FROM {tabla}
                    WHERE {columna} = %s
                    FOR UPDATE
                """, (id_titular,))
                titular = cursor.fetchone()
                if titular is None:
                    raise ValueError(f"El {tipo.lower()} no existe.")
                if titular[0] != "ACTIVO":
                    raise ValueError(
                        f"El {tipo.lower()} está inactivo: no se registran "
                        "facturas nuevas (sí se pueden pagar las pendientes)."
                    )

                if tipo == "OPERADOR":
                    cursor.execute("""
                        SELECT t.id_operador, e.estado,
                               (e.fecha_entrega AT TIME ZONE %s)::date
                        FROM tramo t
                        JOIN envio e ON e.id_envio = t.id_envio
                        WHERE t.id_tramo = %s
                        FOR UPDATE OF t FOR SHARE OF e
                    """, (ZONA_CONTABLE, id_tramo))
                    tramo = cursor.fetchone()
                    if tramo is None:
                        raise ValueError("El tramo no existe.")
                    operador_tramo, estado_envio, dia_entrega = tramo
                    if operador_tramo is None:
                        raise ValueError("El tramo no tiene operador asignado.")
                    if operador_tramo != id_titular:
                        raise ValueError(
                            "El tramo no fue realizado por este operador."
                        )
                    if not envio_entregado(estado_envio):
                        raise ValueError(
                            "Solo se puede facturar un tramo cuyo envío está "
                            f"Entregado (estado actual: {estado_envio})."
                        )
                    if dia_entrega is None:
                        raise ValueError(
                            "El envío no tiene fecha real de entrega."
                        )
                    if fecha_emision < dia_entrega:
                        raise ValueError(
                            "La factura del operador no puede ser anterior a "
                            f"la entrega del envío ({dia_entrega:%d/%m/%Y})."
                        )
                    cursor.execute("""
                        SELECT 1 FROM factura_recibida
                        WHERE id_tramo = %s AND estado <> 'Anulada'
                    """, (id_tramo,))
                    if cursor.fetchone() is not None:
                        raise ValueError(
                            "El tramo ya tiene una factura registrada."
                        )

                cursor.execute(f"""
                    SELECT 1 FROM factura_recibida
                    WHERE {columna} = %s AND upper(numero_comprobante) = %s
                """, (id_titular, numero))
                if cursor.fetchone() is not None:
                    raise ValueError(
                        "Ese número de comprobante ya fue registrado para este "
                        f"{tipo.lower()}."
                    )

                id_cuenta, moneda = _bloquear_o_crear_cuenta(
                    cursor, columna, id_titular
                )
                if moneda != MONEDA_TERCEROS:
                    raise ValueError("La cuenta no está en ARS.")

                cursor.execute(f"""
                    INSERT INTO factura_recibida (
                        {columna}, numero_comprobante, fecha_emision,
                        fecha_vencimiento, total, moneda, estado,
                        id_tramo, concepto, registrado_por
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, 'Pendiente', %s, %s, %s)
                    RETURNING id_factura_recibida
                """, (
                    id_titular, numero, fecha_emision, fecha_vencimiento,
                    total, moneda, id_tramo, concepto, registrado_por,
                ))
                id_factura = cursor.fetchone()[0]

                cursor.execute("""
                    UPDATE cuenta_corriente_tercero
                    SET saldo = saldo + %s,
                        fecha_actualizacion = CURRENT_TIMESTAMP
                    WHERE id_cuenta_tercero = %s
                """, (total, id_cuenta))
                if cursor.rowcount != 1:
                    raise ValueError("No se pudo actualizar la cuenta corriente.")

                cursor.execute("""
                    INSERT INTO movimiento_cuenta_tercero (
                        id_cuenta_tercero, moneda, tipo_movimiento,
                        importe_firmado, fecha_contable, tipo_origen,
                        referencia_origen, referencia_documental
                    )
                    VALUES (%s, %s, 'FACTURA_RECIBIDA', %s, %s,
                            'FACTURA_RECIBIDA', %s, %s)
                """, (
                    id_cuenta, moneda, total, fecha_emision,
                    str(id_factura),
                    f"{tipo.lower()}={id_titular};comprobante={numero}",
                ))

                return id_factura
    except errors.UniqueViolation:
        # Carrera con otra carga simultánea del mismo comprobante o tramo.
        raise ValueError(
            "La factura ya fue registrada (comprobante o tramo duplicado)."
        ) from None


def registrar_pago_emitido(
    id_factura_recibida, monto, metodo_pago, referencia=None, registrado_por=None
):
    """Registra un pago nuestro a una factura recibida.

    Se permite pagar aunque el titular esté inactivo: la deuda sigue
    existiendo. Devuelve (id_pago_emitido, nuevo_estado_factura).
    """
    monto = importe_positivo(monto, "El pago debe ser mayor a cero.")
    metodo_pago = str(metodo_pago or "").strip()
    if not metodo_pago:
        raise ValueError("Falta el método de pago.")
    referencia = str(referencia or "").strip() or None

    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT id_proveedor, id_operador, total, estado, moneda
                FROM factura_recibida
                WHERE id_factura_recibida = %s
                FOR UPDATE
            """, (id_factura_recibida,))
            factura = cursor.fetchone()
            if factura is None:
                raise ValueError("La factura no existe.")

            id_proveedor, id_operador, total, estado, moneda_factura = factura
            if estado == "Anulada":
                raise ValueError("No se puede pagar una factura anulada.")

            cursor.execute("""
                SELECT COALESCE(SUM(monto), 0)
                FROM pago_emitido
                WHERE id_factura_recibida = %s
            """, (id_factura_recibida,))
            pendiente = total - cursor.fetchone()[0]

            if pendiente <= 0:
                raise ValueError("La factura ya está pagada.")
            if monto > pendiente:
                raise ValueError(
                    f"El pago supera el saldo pendiente: ${pendiente:.2f}"
                )

            columna = "id_proveedor" if id_proveedor is not None else "id_operador"
            id_titular = id_proveedor if id_proveedor is not None else id_operador

            cursor.execute(f"""
                SELECT id_cuenta_tercero, moneda
                FROM cuenta_corriente_tercero
                WHERE {columna} = %s
                FOR UPDATE
            """, (id_titular,))
            cuenta = cursor.fetchone()
            if cuenta is None:
                raise ValueError("El titular no tiene cuenta corriente.")
            id_cuenta, moneda_cuenta = cuenta
            if moneda_cuenta != moneda_factura:
                raise ValueError(
                    "La moneda de la factura no coincide con la de la cuenta."
                )

            cursor.execute("""
                INSERT INTO pago_emitido (
                    id_factura_recibida, monto, metodo_pago, referencia,
                    registrado_por
                )
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id_pago_emitido, (fecha AT TIME ZONE %s)::date
            """, (
                id_factura_recibida, monto, metodo_pago, referencia,
                registrado_por, ZONA_CONTABLE,
            ))
            id_pago, fecha_contable = cursor.fetchone()

            nuevo_estado = "Pagada" if monto == pendiente else "Parcial"
            cursor.execute("""
                UPDATE factura_recibida SET estado = %s
                WHERE id_factura_recibida = %s
            """, (nuevo_estado, id_factura_recibida))

            cursor.execute("""
                UPDATE cuenta_corriente_tercero
                SET saldo = saldo - %s,
                    fecha_actualizacion = CURRENT_TIMESTAMP
                WHERE id_cuenta_tercero = %s
            """, (monto, id_cuenta))
            if cursor.rowcount != 1:
                raise ValueError("No se pudo actualizar la cuenta corriente.")

            cursor.execute("""
                INSERT INTO movimiento_cuenta_tercero (
                    id_cuenta_tercero, moneda, tipo_movimiento,
                    importe_firmado, fecha_contable, tipo_origen,
                    referencia_origen, referencia_documental
                )
                VALUES (%s, %s, 'PAGO_EMITIDO', %s, %s,
                        'PAGO_EMITIDO', %s, %s)
            """, (
                id_cuenta, moneda_factura, -monto, fecha_contable,
                str(id_pago),
                f"factura_recibida={id_factura_recibida};metodo={metodo_pago}",
            ))

            return id_pago, nuevo_estado


def consultar_cuenta_tercero(tipo_titular, id_titular):
    """Saldo y totales del titular, o None si todavía no tiene cuenta."""
    _, _, columna = _titular(tipo_titular)
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute(f"""
                WITH facturado AS (
                    SELECT COUNT(*) AS cantidad, COALESCE(SUM(total), 0) AS total
                    FROM factura_recibida
                    WHERE {columna} = %s AND estado <> 'Anulada'
                ),
                pagado AS (
                    SELECT COALESCE(SUM(p.monto), 0) AS total
                    FROM pago_emitido p
                    JOIN factura_recibida f
                      ON f.id_factura_recibida = p.id_factura_recibida
                    WHERE f.{columna} = %s
                )
                SELECT cc.saldo, cc.moneda, cc.fecha_actualizacion,
                       fa.cantidad, fa.total, pa.total
                FROM cuenta_corriente_tercero cc
                CROSS JOIN facturado fa
                CROSS JOIN pagado pa
                WHERE cc.{columna} = %s
            """, (id_titular, id_titular, id_titular))
            fila = cursor.fetchone()

    if fila is None:
        return None
    return {
        "saldo": fila[0],
        "moneda": fila[1],
        "fecha_actualizacion": fila[2],
        "cantidad_facturas": fila[3],
        "facturado": fila[4],
        "pagado": fila[5],
    }


def listar_facturas_pendientes(tipo_titular, id_titular):
    _, _, columna = _titular(tipo_titular)
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute(f"""
                SELECT f.id_factura_recibida, f.numero_comprobante,
                       f.fecha_emision, f.fecha_vencimiento, f.total,
                       COALESCE(SUM(p.monto), 0) AS pagado,
                       f.total - COALESCE(SUM(p.monto), 0) AS pendiente,
                       f.estado, f.id_tramo, f.concepto
                FROM factura_recibida f
                LEFT JOIN pago_emitido p
                  ON p.id_factura_recibida = f.id_factura_recibida
                WHERE f.{columna} = %s
                  AND f.estado IN ('Pendiente', 'Parcial')
                GROUP BY f.id_factura_recibida
                ORDER BY f.fecha_vencimiento, f.id_factura_recibida
            """, (id_titular,))
            return cursor.fetchall()


def listar_movimientos_tercero(tipo_titular, id_titular):
    _, _, columna = _titular(tipo_titular)
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute(f"""
                SELECT m.fecha_contable, m.tipo_movimiento, m.importe_firmado,
                       m.referencia_origen, m.referencia_documental
                FROM movimiento_cuenta_tercero m
                JOIN cuenta_corriente_tercero cc
                  ON cc.id_cuenta_tercero = m.id_cuenta_tercero
                WHERE cc.{columna} = %s
                ORDER BY m.fecha_contable, m.id_movimiento
            """, (id_titular,))
            return cursor.fetchall()


def listar_vencimientos(dias=7, hoy=None):
    """Facturas recibidas impagas vencidas o que vencen en los próximos días.

    Devuelve filas con días hasta el vencimiento (negativo = vencida).
    """
    dias = int(dias)
    if dias < 0:
        raise ValueError("Los días deben ser cero o más.")
    hoy = hoy or hoy_contable()
    limite = hoy + timedelta(days=dias)

    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT f.id_factura_recibida,
                       CASE WHEN f.id_proveedor IS NOT NULL
                            THEN 'PROVEEDOR' ELSE 'OPERADOR' END AS tipo,
                       COALESCE(pr.razon_social, op.razon_social) AS titular,
                       f.numero_comprobante, f.fecha_emision,
                       f.fecha_vencimiento,
                       f.fecha_vencimiento - %s::date AS dias_restantes,
                       f.total,
                       f.total - COALESCE(SUM(p.monto), 0) AS pendiente,
                       f.estado
                FROM factura_recibida f
                LEFT JOIN proveedor pr ON pr.id_proveedor = f.id_proveedor
                LEFT JOIN operador_logistico op
                       ON op.id_operador = f.id_operador
                LEFT JOIN pago_emitido p
                       ON p.id_factura_recibida = f.id_factura_recibida
                WHERE f.estado IN ('Pendiente', 'Parcial')
                  AND f.fecha_vencimiento <= %s
                GROUP BY f.id_factura_recibida, pr.razon_social,
                         op.razon_social
                ORDER BY f.fecha_vencimiento, f.id_factura_recibida
            """, (hoy, limite))
            return cursor.fetchall()


def listar_tramos_facturables(id_operador):
    """Tramos del operador con envío Entregado y sin factura vigente."""
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT t.id_tramo, t.id_envio, t.medio_transporte,
                       t.origen, t.destino, t.fecha_salida
                FROM tramo t
                JOIN envio e ON e.id_envio = t.id_envio
                WHERE t.id_operador = %s
                  AND LOWER(e.estado) = 'entregado'
                  AND e.fecha_entrega IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1 FROM factura_recibida f
                      WHERE f.id_tramo = t.id_tramo AND f.estado <> 'Anulada'
                  )
                ORDER BY t.fecha_salida, t.id_tramo
            """, (id_operador,))
            return cursor.fetchall()
