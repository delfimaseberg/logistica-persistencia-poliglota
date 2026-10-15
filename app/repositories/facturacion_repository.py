
from decimal import Decimal
from app.database.postgres_connection import get_postgres_connection


def listar_clientes_facturacion():
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT id_cliente, razon_social, cuit
                FROM cliente
                WHERE UPPER(estado) = 'ACTIVO'
                ORDER BY razon_social
            """)
            return cursor.fetchall()


def listar_facturas_cliente(id_cliente):
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT f.id_factura, f.fecha_emision, f.total,
                       f.estado, COALESCE(SUM(p.monto), 0) AS pagado,
                       f.total - COALESCE(SUM(p.monto), 0) AS pendiente
                FROM factura f
                LEFT JOIN pago p ON p.id_factura = f.id_factura
                WHERE f.id_cliente = %s
                GROUP BY f.id_factura, f.fecha_emision,
                         f.total, f.estado
                ORDER BY f.id_factura DESC
            """, (id_cliente,))
            return cursor.fetchall()


def emitir_factura(id_cliente, total):
    total = Decimal(str(total))
    if total <= 0:
        raise ValueError("El importe debe ser mayor a cero.")

    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT id_cliente
                FROM cliente
                WHERE id_cliente = %s AND UPPER(estado) = 'ACTIVO'
                FOR UPDATE
            """, (id_cliente,))
            if cursor.fetchone() is None:
                raise ValueError("El cliente no existe o no está activo.")

            cursor.execute("""
                INSERT INTO factura
                    (id_cliente, fecha_emision, total, estado)
                VALUES (%s, CURRENT_DATE, %s, 'Pendiente')
                RETURNING id_factura
            """, (id_cliente, total))
            id_factura = cursor.fetchone()[0]

            cursor.execute("""
                INSERT INTO cuenta_corriente
                    (id_cliente, saldo, fecha_actualizacion)
                VALUES (%s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (id_cliente)
                DO UPDATE SET
                    saldo = cuenta_corriente.saldo + EXCLUDED.saldo,
                    fecha_actualizacion = CURRENT_TIMESTAMP
            """, (id_cliente, total))

            return id_factura


def registrar_pago(id_factura, monto, metodo_pago):
    monto = Decimal(str(monto))
    if monto <= 0:
        raise ValueError("El pago debe ser mayor a cero.")

    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT id_cliente, total, estado
                FROM factura
                WHERE id_factura = %s
                FOR UPDATE
            """, (id_factura,))
            factura = cursor.fetchone()

            if factura is None:
                raise ValueError("La factura no existe.")

            id_cliente, total, estado = factura
            if estado.lower() == "anulada":
                raise ValueError("No se puede pagar una factura anulada.")

            cursor.execute("""
                SELECT COALESCE(SUM(monto), 0)
                FROM pago
                WHERE id_factura = %s
            """, (id_factura,))
            pagado = cursor.fetchone()[0]
            pendiente = total - pagado

            if pendiente <= 0:
                raise ValueError("La factura ya está pagada.")

            if monto > pendiente:
                raise ValueError(
                    f"El pago supera el saldo pendiente: ${pendiente:.2f}"
                )

            cursor.execute("""
                INSERT INTO pago (id_factura, monto, metodo_pago)
                VALUES (%s, %s, %s)
                RETURNING id_pago
            """, (id_factura, monto, metodo_pago))
            id_pago = cursor.fetchone()[0]

            nuevo_estado = "Pagada" if monto == pendiente else "Parcial"
            cursor.execute("""
                UPDATE factura
                SET estado = %s
                WHERE id_factura = %s
            """, (nuevo_estado, id_factura))

            cursor.execute("""
                INSERT INTO cuenta_corriente
                    (id_cliente, saldo, fecha_actualizacion)
                VALUES (%s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (id_cliente)
                DO UPDATE SET
                    saldo = cuenta_corriente.saldo + EXCLUDED.saldo,
                    fecha_actualizacion = CURRENT_TIMESTAMP
            """, (id_cliente, -monto))

            return id_pago, nuevo_estado


def consultar_cuenta_corriente(id_cliente):
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT c.id_cliente, c.razon_social,
                       COALESCE(SUM(f.total), 0) AS facturado,
                       COALESCE((
                           SELECT SUM(p.monto)
                           FROM pago p
                           JOIN factura f2 ON f2.id_factura = p.id_factura
                           WHERE f2.id_cliente = c.id_cliente
                       ), 0) AS pagado
                FROM cliente c
                LEFT JOIN factura f ON f.id_cliente = c.id_cliente
                WHERE c.id_cliente = %s
                GROUP BY c.id_cliente, c.razon_social
            """, (id_cliente,))
            return cursor.fetchone()


def reporte_facturacion_clientes():
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT c.id_cliente, c.razon_social,
                       COUNT(f.id_factura) AS cantidad_facturas,
                       COALESCE(SUM(f.total), 0) AS facturado,
                       COALESCE((
                           SELECT SUM(p.monto)
                           FROM pago p
                           JOIN factura f2 ON f2.id_factura = p.id_factura
                           WHERE f2.id_cliente = c.id_cliente
                       ), 0) AS cobrado
                FROM cliente c
                LEFT JOIN factura f ON f.id_cliente = c.id_cliente
                GROUP BY c.id_cliente, c.razon_social
                ORDER BY facturado DESC, c.razon_social
            """)
            return cursor.fetchall()


def reporte_envios_estado():
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT estado, COUNT(*)
                FROM envio
                GROUP BY estado
                ORDER BY COUNT(*) DESC, estado
            """)
            return cursor.fetchall()


def reporte_ingresos_mensuales():
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT TO_CHAR(
                           DATE_TRUNC('month', fecha AT TIME ZONE
                                      'America/Argentina/Buenos_Aires'),
                           'YYYY-MM'
                       ) AS mes,
                       COUNT(*) AS cantidad_pagos,
                       SUM(monto) AS total
                FROM pago
                GROUP BY DATE_TRUNC(
                    'month',
                    fecha AT TIME ZONE 'America/Argentina/Buenos_Aires'
                )
                ORDER BY mes DESC
                LIMIT 12
            """)
            return cursor.fetchall()
