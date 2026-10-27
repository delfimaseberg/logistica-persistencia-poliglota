
from decimal import Decimal
from app.database.postgres_connection import get_postgres_connection


def listar_envios_entregados_candidatos_facturacion():
    """Lista envíos entregados para revisión de posible facturación.

    La tabla factura aún no referencia un envío y el esquema no contiene una
    fuente de importes. Esta consulta identifica candidatos; no determina si
    ya fueron facturados ni autoriza la emisión.
    """
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT id_envio, id_cliente, estado
                FROM envio
                WHERE LOWER(TRIM(estado)) = 'entregado'
                ORDER BY id_envio
            """)
            return cursor.fetchall()


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


def obtener_contexto_tarifas_aprobadas(id_envio):
    """Devuelve tarifas aprobadas y configuración asociada, sin emitir."""
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT t.id_tarifa, t.id_envio, t.version,
                       t.importe_base, t.importe_impuestos, t.importe_total,
                       t.moneda, t.id_configuracion_fiscal,
                       t.tratamiento_impositivo, t.tasa_impositiva,
                       t.estado, t.referencia_aprobacion,
                       t.aprobado_por, t.aprobado_en,
                       f.codigo, f.version, f.tratamiento, f.tasa,
                       f.vigente_desde, f.vigente_hasta,
                       f.referencia_aprobacion, f.aprobado_por,
                       f.aprobado_en, f.activa,
                       cc.moneda
                FROM tarifa_envio t
                JOIN configuracion_fiscal f
                  ON f.id_configuracion_fiscal = t.id_configuracion_fiscal
                JOIN envio e ON e.id_envio = t.id_envio
                LEFT JOIN cuenta_corriente cc ON cc.id_cliente = e.id_cliente
                WHERE t.id_envio = %s
                  AND t.estado = 'APROBADA'
                ORDER BY t.version DESC
            """, (id_envio,))
            filas = cursor.fetchall()

    resultados = []
    for fila in filas:
        tarifa = {
            "id_tarifa": fila[0],
            "id_envio": fila[1],
            "version": fila[2],
            "importe_base": fila[3],
            "importe_impuestos": fila[4],
            "importe_total": fila[5],
            "moneda": fila[6],
            "id_configuracion_fiscal": fila[7],
            "tratamiento_impositivo": fila[8],
            "tasa_impositiva": fila[9],
            "estado": fila[10],
            "referencia_aprobacion": fila[11],
            "aprobado_por": fila[12],
            "aprobado_en": fila[13],
        }
        configuracion = {
            "id_configuracion_fiscal": fila[7],
            "codigo": fila[14],
            "version": fila[15],
            "tratamiento": fila[16],
            "tasa": fila[17],
            "vigente_desde": fila[18],
            "vigente_hasta": fila[19],
            "referencia_aprobacion": fila[20],
            "aprobado_por": fila[21],
            "aprobado_en": fila[22],
            # Solo se almacenan perfiles fiscales con aprobador y referencia.
            "aprobada": True,
            "activa": fila[23],
        }
        resultados.append({
            "tarifa": tarifa,
            "configuracion_fiscal": configuracion,
            "moneda_cuenta": fila[24],
        })
    return resultados


def existe_factura_original(id_envio, evento_entrega_id):
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT 1
                FROM factura
                WHERE id_envio = %s OR evento_entrega_id = %s
                LIMIT 1
            """, (id_envio, str(evento_entrega_id)))
            return cursor.fetchone() is not None


def contar_facturas_sin_envio_cliente(id_cliente):
    """Cuenta facturas no conciliadas a un envío; no atribuye ninguna."""
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT COUNT(*)
                FROM factura
                WHERE id_cliente = %s AND id_envio IS NULL
            """, (id_cliente,))
            return cursor.fetchone()[0]


def registrar_auditoria_facturacion(
    id_envio,
    envio_id_reportado,
    evento_entrega_id,
    resultado,
    motivo,
    id_factura=None,
):
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                INSERT INTO auditoria_facturacion_periodica (
                    id_envio, envio_id_reportado, evento_entrega_id,
                    resultado, motivo, id_factura
                )
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                id_envio,
                envio_id_reportado,
                str(evento_entrega_id) if evento_entrega_id else None,
                resultado,
                str(motivo)[:2000],
                id_factura,
            ))


def emitir_factura_automatica(
    id_envio, evento_entrega_id, fecha_entrega, fecha_emision, id_tarifa
):
    """Emite factura y movimiento en una transacción PostgreSQL."""
    from app.utils.validaciones_financieras import validar_tarifa_aprobada

    evento_entrega_id = str(evento_entrega_id)

    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            # Bloquear la fila del cliente serializa este flujo con emitir_factura,
            # que ya toma el mismo bloqueo antes de crear una factura manual.
            cursor.execute("""
                SELECT e.id_cliente, e.estado, c.estado
                FROM envio e
                JOIN cliente c ON c.id_cliente = e.id_cliente
                WHERE e.id_envio = %s
                FOR UPDATE OF e, c
            """, (id_envio,))
            envio = cursor.fetchone()
            if envio is None:
                raise ValueError("El envío no existe en PostgreSQL.")
            id_cliente, estado_envio, estado_cliente = envio
            if str(estado_envio).strip().casefold() != "entregado":
                raise ValueError(
                    "El estado del envío dejó de ser Entregado antes de emitir."
                )
            if str(estado_cliente).strip().upper() != "ACTIVO":
                raise ValueError("El cliente no está activo.")

            cursor.execute("""
                SELECT moneda
                FROM cuenta_corriente
                WHERE id_cliente = %s
                FOR UPDATE
            """, (id_cliente,))
            cuenta = cursor.fetchone()
            if cuenta is None or not cuenta[0]:
                raise ValueError(
                    "La cuenta corriente no tiene moneda explícitamente configurada."
                )
            moneda_cuenta = cuenta[0]

            cursor.execute("""
                SELECT 1
                FROM factura
                WHERE id_envio = %s OR evento_entrega_id = %s
                LIMIT 1
            """, (id_envio, evento_entrega_id))
            if cursor.fetchone() is not None:
                raise ValueError(
                    "Ya existe una factura original para el envío o evento."
                )

            # Las facturas manuales anteriores no identifican envíos. No se
            # puede descartar que cubran este envío, por lo que se bloquea.
            cursor.execute("""
                SELECT COUNT(*)
                FROM factura
                WHERE id_cliente = %s AND id_envio IS NULL
            """, (id_cliente,))
            if cursor.fetchone()[0]:
                raise ValueError(
                    "Hay facturas sin vínculo a envío para este cliente; "
                    "conciliarlas antes de la facturación automática."
                )

            cursor.execute("""
                SELECT t.id_tarifa, t.id_envio, t.version,
                       t.importe_base, t.importe_impuestos, t.importe_total,
                       t.moneda, t.id_configuracion_fiscal,
                       t.tratamiento_impositivo, t.tasa_impositiva,
                       t.estado, t.referencia_aprobacion,
                       t.aprobado_por, t.aprobado_en,
                       f.codigo, f.version, f.tratamiento, f.tasa,
                       f.vigente_desde, f.vigente_hasta,
                       f.referencia_aprobacion, f.aprobado_por,
                       f.aprobado_en, f.activa
                FROM tarifa_envio t
                JOIN configuracion_fiscal f
                  ON f.id_configuracion_fiscal = t.id_configuracion_fiscal
                WHERE t.id_tarifa = %s
                  AND t.id_envio = %s
                  AND t.estado = 'APROBADA'
                  AND f.activa = TRUE
                FOR UPDATE OF t, f
            """, (id_tarifa, id_envio))
            fila = cursor.fetchone()
            if fila is None:
                raise ValueError(
                    "La tarifa aprobada o su configuración fiscal ya no están vigentes."
                )

            tarifa = {
                "id_tarifa": fila[0],
                "id_envio": fila[1],
                "version": fila[2],
                "importe_base": fila[3],
                "importe_impuestos": fila[4],
                "importe_total": fila[5],
                "moneda": fila[6],
                "id_configuracion_fiscal": fila[7],
                "tratamiento_impositivo": fila[8],
                "tasa_impositiva": fila[9],
                "estado": fila[10],
                "referencia_aprobacion": fila[11],
                "aprobado_por": fila[12],
                "aprobado_en": fila[13],
            }
            configuracion = {
                "id_configuracion_fiscal": fila[7],
                "codigo": fila[14],
                "version": fila[15],
                "tratamiento": fila[16],
                "tasa": fila[17],
                "vigente_desde": fila[18],
                "vigente_hasta": fila[19],
                "referencia_aprobacion": fila[20],
                "aprobado_por": fila[21],
                "aprobado_en": fila[22],
                "aprobada": True,
                "activa": fila[23],
            }
            importes = validar_tarifa_aprobada(
                tarifa, moneda_cuenta, configuracion, fecha_emision
            )

            cursor.execute("""
                INSERT INTO factura (
                    id_cliente, fecha_emision, total, estado,
                    id_envio, id_tarifa, evento_entrega_id, fecha_entrega,
                    origen_emision, moneda, importe_base, importe_impuestos,
                    id_configuracion_fiscal, tratamiento_impositivo,
                    tasa_impositiva
                )
                VALUES (
                    %s, %s, %s, 'Pendiente',
                    %s, %s, %s, %s, 'AUTOMATICA', %s,
                    %s, %s, %s, %s, %s
                )
                RETURNING id_factura
            """, (
                id_cliente,
                fecha_emision,
                importes["importe_total"],
                id_envio,
                tarifa["id_tarifa"],
                evento_entrega_id,
                fecha_entrega,
                importes["moneda"],
                importes["importe_base"],
                importes["importe_impuestos"],
                tarifa["id_configuracion_fiscal"],
                tarifa["tratamiento_impositivo"],
                tarifa["tasa_impositiva"],
            ))
            id_factura = cursor.fetchone()[0]

            cursor.execute("""
                UPDATE cuenta_corriente
                SET saldo = saldo + %s,
                    fecha_actualizacion = CURRENT_TIMESTAMP
                WHERE id_cliente = %s
            """, (importes["importe_total"], id_cliente))
            if cursor.rowcount != 1:
                raise ValueError("No se pudo actualizar la cuenta corriente.")

            cursor.execute("""
                INSERT INTO movimiento_cuenta_corriente (
                    id_cliente, moneda, tipo_movimiento, importe_firmado,
                    fecha_contable, tipo_origen, referencia_origen,
                    referencia_documental
                )
                VALUES (%s, %s, 'FACTURA', %s, %s, 'FACTURA', %s, %s)
            """, (
                id_cliente,
                importes["moneda"],
                importes["importe_total"],
                fecha_emision,
                str(id_factura),
                f"envio={id_envio};evento_entrega={evento_entrega_id}",
            ))

            cursor.execute("""
                INSERT INTO auditoria_facturacion_periodica (
                    id_envio, envio_id_reportado, evento_entrega_id,
                    resultado, motivo, id_factura
                )
                VALUES (%s, %s, %s, 'FACTURADA', %s, %s)
            """, (
                id_envio,
                id_envio,
                evento_entrega_id,
                "Factura automática emitida con tarifa aprobada.",
                id_factura,
            ))

            return id_factura
