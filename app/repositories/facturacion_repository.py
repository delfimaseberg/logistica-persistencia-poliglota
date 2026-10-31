
from decimal import Decimal, InvalidOperation

from psycopg import errors

from app.database.postgres_connection import get_postgres_connection
from app.services.cotizacion_envio import (
    CODIGO_TARIFA,
    TASA_IVA,
    TRATAMIENTO_IVA,
    CotizacionImposible,
    calcular_iva,
    cotizar,
)

# Moneda única del proyecto. Solo se usa al crear una cuenta corriente nueva
# para un cliente que todavía no tiene ninguna factura; nunca se completa
# sobre cuentas o facturas existentes desde el código.
MONEDA_PROYECTO = "ARS"

# Las fechas contables (emisión de factura y fecha de pago) se determinan en
# este calendario, igual que en el cierre mensual (cierre_cuenta_service).
ZONA_CONTABLE = "America/Argentina/Buenos_Aires"


def _importe_positivo(valor, mensaje):
    """Convierte a Decimal con 2 decimales y exige que sea mayor a cero.

    Se redondea antes de validar para que un importe como 0.001 no termine
    guardado como 0.00 (la columna es NUMERIC(14,2)).
    """
    try:
        importe = Decimal(str(valor))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(mensaje)
    if not importe.is_finite():
        raise ValueError(mensaje)
    importe = importe.quantize(Decimal("0.01"))
    if importe <= 0:
        raise ValueError(mensaje)
    return importe


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


def _obtener_moneda_cuenta_para_factura(cursor, id_cliente):
    """Bloquea la cuenta del cliente y devuelve su moneda.

    - Si la cuenta existe, debe tener moneda configurada (no se completa acá).
    - Si no existe y el cliente no tiene facturas previas, se crea con saldo
      cero y la moneda del proyecto: no hay historia que se esté inventando.
    - Si no existe pero el cliente ya tiene facturas, los datos están
      inconsistentes y se bloquea para conciliar a mano.
    """
    cursor.execute("""
        SELECT moneda
        FROM cuenta_corriente
        WHERE id_cliente = %s
        FOR UPDATE
    """, (id_cliente,))
    cuenta = cursor.fetchone()

    if cuenta is not None:
        moneda = str(cuenta[0] or "").strip().upper()
        if not moneda:
            raise ValueError(
                "La cuenta corriente del cliente no tiene moneda configurada. "
                "Configurarla explícitamente antes de facturar."
            )
        return moneda

    cursor.execute("""
        SELECT 1
        FROM factura
        WHERE id_cliente = %s
        LIMIT 1
    """, (id_cliente,))
    if cursor.fetchone() is not None:
        raise ValueError(
            "El cliente tiene facturas pero no tiene cuenta corriente; "
            "conciliar antes de emitir nuevas facturas."
        )

    cursor.execute("""
        INSERT INTO cuenta_corriente
            (id_cliente, saldo, moneda, fecha_actualizacion)
        VALUES (%s, 0, %s, CURRENT_TIMESTAMP)
        RETURNING moneda
    """, (id_cliente, MONEDA_PROYECTO))
    return cursor.fetchone()[0]


def registrar_pago(id_factura, monto, metodo_pago):
    """Registra un pago y lo descuenta de la cuenta corriente.

    En una sola transacción: crea el pago, actualiza el estado de la factura,
    resta el importe del saldo y registra un movimiento PAGO negativo.
    """
    monto = _importe_positivo(monto, "El pago debe ser mayor a cero.")
    metodo_pago = str(metodo_pago or "").strip()
    if not metodo_pago:
        raise ValueError("Falta el método de pago.")

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

            # Moneda: la del pago es la de la factura y debe coincidir con la
            # de la cuenta. No se asume ARS para facturas sin moneda.
            cursor.execute("""
                SELECT moneda
                FROM factura
                WHERE id_factura = %s
            """, (id_factura,))
            moneda_factura = str(cursor.fetchone()[0] or "").strip().upper()
            if not moneda_factura:
                raise ValueError(
                    f"La factura {id_factura} no tiene moneda registrada. "
                    "Configurarla explícitamente antes de registrar pagos."
                )

            cursor.execute("""
                SELECT moneda
                FROM cuenta_corriente
                WHERE id_cliente = %s
                FOR UPDATE
            """, (id_cliente,))
            cuenta = cursor.fetchone()
            if cuenta is None:
                raise ValueError("El cliente no tiene cuenta corriente.")
            moneda_cuenta = str(cuenta[0] or "").strip().upper()
            if moneda_cuenta != moneda_factura:
                raise ValueError(
                    "La moneda de la factura no coincide con la de la cuenta "
                    "corriente (o la cuenta no tiene moneda configurada)."
                )

            cursor.execute("""
                INSERT INTO pago (id_factura, monto, metodo_pago)
                VALUES (%s, %s, %s)
                RETURNING id_pago, (fecha AT TIME ZONE %s)::date
            """, (id_factura, monto, metodo_pago, ZONA_CONTABLE))
            id_pago, fecha_contable = cursor.fetchone()

            nuevo_estado = "Pagada" if monto == pendiente else "Parcial"
            cursor.execute("""
                UPDATE factura
                SET estado = %s
                WHERE id_factura = %s
            """, (nuevo_estado, id_factura))

            cursor.execute("""
                UPDATE cuenta_corriente
                SET saldo = saldo - %s,
                    fecha_actualizacion = CURRENT_TIMESTAMP
                WHERE id_cliente = %s
            """, (monto, id_cliente))
            if cursor.rowcount != 1:
                raise ValueError("No se pudo actualizar la cuenta corriente.")

            cursor.execute("""
                INSERT INTO movimiento_cuenta_corriente (
                    id_cliente, moneda, tipo_movimiento, importe_firmado,
                    fecha_contable, tipo_origen, referencia_origen,
                    referencia_documental
                )
                VALUES (%s, %s, 'PAGO', %s, %s, 'PAGO', %s, %s)
            """, (
                id_cliente,
                moneda_factura,
                -monto,
                fecha_contable,
                str(id_pago),
                f"factura={id_factura};metodo={metodo_pago}",
            ))

            return id_pago, nuevo_estado


def consultar_cuenta_corriente(id_cliente):
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            # Facturas y pagos se agregan por separado y recién después se
            # unen al cliente: así una factura con varios pagos no se suma
            # más de una vez. Las facturas anuladas no forman deuda.
            cursor.execute("""
                WITH facturado AS (
                    SELECT id_cliente, SUM(total) AS total
                    FROM factura
                    WHERE id_cliente = %s
                      AND LOWER(TRIM(estado)) <> 'anulada'
                    GROUP BY id_cliente
                ),
                pagado AS (
                    SELECT f.id_cliente, SUM(p.monto) AS total
                    FROM pago p
                    JOIN factura f ON f.id_factura = p.id_factura
                    WHERE f.id_cliente = %s
                    GROUP BY f.id_cliente
                )
                SELECT c.id_cliente, c.razon_social,
                       COALESCE(fa.total, 0) AS facturado,
                       COALESCE(pa.total, 0) AS pagado
                FROM cliente c
                LEFT JOIN facturado fa ON fa.id_cliente = c.id_cliente
                LEFT JOIN pagado pa ON pa.id_cliente = c.id_cliente
                WHERE c.id_cliente = %s
            """, (id_cliente, id_cliente, id_cliente))
            return cursor.fetchone()


def consultar_movimientos_cuenta(id_cliente):
    """Lista el ledger de la cuenta (solo lectura), del más antiguo al último."""
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT id_movimiento, fecha_contable, tipo_movimiento,
                       importe_firmado, moneda, tipo_origen,
                       referencia_origen, referencia_documental
                FROM movimiento_cuenta_corriente
                WHERE id_cliente = %s
                ORDER BY fecha_contable, id_movimiento
            """, (id_cliente,))
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


class FacturaExistente(ValueError):
    """El envío ya tiene factura (índice único uq_factura_original_envio)."""


ORIGENES_ENVIO = ("ENVIO_MANUAL", "ENVIO_AUTOMATICA")


def listar_facturas_cliente(id_cliente):
    """Facturas del cliente. Columnas 0-5 como antes; 6 id_envio,
    7 neto, 8 IVA, 9 origen de emisión (None = histórica)."""
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT f.id_factura, f.fecha_emision, f.total,
                       f.estado, COALESCE(SUM(p.monto), 0) AS pagado,
                       f.total - COALESCE(SUM(p.monto), 0) AS pendiente,
                       f.id_envio, f.importe_base, f.importe_impuestos,
                       f.origen_emision
                FROM factura f
                LEFT JOIN pago p ON p.id_factura = f.id_factura
                WHERE f.id_cliente = %s
                GROUP BY f.id_factura
                ORDER BY f.id_factura DESC
            """, (id_cliente,))
            return cursor.fetchall()


def _regla_vigente(cursor, bloquear=False):
    """Versión APROBADA de TARIFA_ESTANDAR con sus componentes.

    Al emitir se bloquea (FOR SHARE) para que no la reemplacen a mitad de
    la transacción; la cotización solo lee.
    """
    cursor.execute(f"""
        SELECT id_regla, version
        FROM regla_tarifaria_version
        WHERE codigo = %s AND estado = 'APROBADA' AND moneda = %s
        {"FOR SHARE" if bloquear else ""}
    """, (CODIGO_TARIFA, MONEDA_PROYECTO))
    regla = cursor.fetchone()
    if regla is None:
        raise CotizacionImposible(
            "No hay una tarifa estándar aprobada. Definir los precios de "
            "transporte antes de cotizar o facturar."
        )
    cursor.execute("""
        SELECT id_componente, criterio, selector, ambito, base_calculo, importe
        FROM regla_tarifaria_componente
        WHERE id_regla = %s
        ORDER BY id_componente
    """, (regla[0],))
    claves = ("id_componente", "criterio", "selector", "ambito",
              "base_calculo", "importe")
    return {
        "id_regla": regla[0],
        "version": regla[1],
        "componentes": [dict(zip(claves, fila)) for fila in cursor.fetchall()],
    }


def _tramos_envio(cursor, id_envio):
    cursor.execute("""
        SELECT id_tramo, medio_transporte, origen, destino
        FROM tramo
        WHERE id_envio = %s
        ORDER BY fecha_salida, id_tramo
    """, (id_envio,))
    claves = ("id_tramo", "medio_transporte", "origen", "destino")
    return [dict(zip(claves, fila)) for fila in cursor.fetchall()]


def cotizar_envio(id_envio):
    """Importe que se facturaría hoy (sin guardar nada)."""
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT e.estado, c.razon_social,
                       EXISTS (SELECT 1 FROM factura f WHERE f.id_envio = e.id_envio)
                FROM envio e
                JOIN cliente c ON c.id_cliente = e.id_cliente
                WHERE e.id_envio = %s
            """, (id_envio,))
            envio = cursor.fetchone()
            if envio is None:
                raise ValueError("El envío no existe.")
            estado, cliente, facturado = envio
            if str(estado).strip().casefold() == "cancelado":
                raise CotizacionImposible("El envío está cancelado.")

            regla = _regla_vigente(cursor)
            resultado = cotizar(_tramos_envio(cursor, id_envio), regla["componentes"])

    resultado.update({
        "id_envio": id_envio,
        "cliente": cliente,
        "estado_envio": estado,
        "facturado": facturado,
        "id_regla": regla["id_regla"],
        "version_regla": regla["version"],
    })
    return resultado


def emitir_factura_envio(id_envio, origen="ENVIO_MANUAL"):
    """Emite la factura de un envío Entregado con la tarifa vigente.

    En una sola transacción: factura + detalle + saldo de cuenta_corriente +
    movimiento FACTURA positivo por el total con IVA. Un envío se factura una
    sola vez (también lo garantiza uq_factura_original_envio).
    """
    if origen not in ORIGENES_ENVIO:
        raise ValueError("Origen de emisión inválido.")

    try:
        with get_postgres_connection() as conexion:
            with conexion.cursor() as cursor:
                # Mismo bloqueo de cliente que los pagos: serializa la cuenta.
                cursor.execute("""
                    SELECT e.id_cliente, e.estado, e.fecha_entrega,
                           (e.fecha_entrega AT TIME ZONE %s)::date,
                           c.estado,
                           (CURRENT_TIMESTAMP AT TIME ZONE %s)::date
                    FROM envio e
                    JOIN cliente c ON c.id_cliente = e.id_cliente
                    WHERE e.id_envio = %s
                    FOR UPDATE OF e, c
                """, (ZONA_CONTABLE, ZONA_CONTABLE, id_envio))
                fila = cursor.fetchone()
                if fila is None:
                    raise ValueError("El envío no existe.")
                (id_cliente, estado, fecha_entrega, dia_entrega,
                 estado_cliente, fecha_emision) = fila

                if str(estado).strip().casefold() != "entregado":
                    raise ValueError(
                        f"El envío no está Entregado (estado: {estado})."
                    )
                if fecha_entrega is None:
                    raise ValueError("El envío no tiene fecha real de entrega.")
                if str(estado_cliente).strip().upper() != "ACTIVO":
                    raise ValueError("El cliente no está activo.")
                if fecha_emision < dia_entrega:
                    raise ValueError(
                        "La fecha de emisión no puede ser anterior a la entrega."
                    )

                cursor.execute(
                    "SELECT id_factura FROM factura WHERE id_envio = %s",
                    (id_envio,),
                )
                existente = cursor.fetchone()
                if existente is not None:
                    raise FacturaExistente(
                        f"El envío ya tiene la factura {existente[0]}."
                    )

                regla = _regla_vigente(cursor, bloquear=True)
                cotizacion = cotizar(
                    _tramos_envio(cursor, id_envio), regla["componentes"]
                )

                moneda = _obtener_moneda_cuenta_para_factura(cursor, id_cliente)
                if moneda != cotizacion["moneda"]:
                    raise ValueError("La cuenta corriente del cliente no está en ARS.")

                cursor.execute("""
                    INSERT INTO factura (
                        id_cliente, fecha_emision, total, estado,
                        origen_emision, moneda, id_envio, id_regla,
                        importe_base, importe_impuestos, tasa_impositiva,
                        tratamiento_impositivo, fecha_entrega
                    )
                    VALUES (%s, %s, %s, 'Pendiente', %s, %s, %s, %s,
                            %s, %s, %s, %s, %s)
                    RETURNING id_factura
                """, (
                    id_cliente, fecha_emision, cotizacion["total"], origen,
                    moneda, id_envio, regla["id_regla"],
                    cotizacion["neto"], cotizacion["iva"],
                    cotizacion["tasa_iva"], cotizacion["tratamiento"],
                    fecha_entrega,
                ))
                id_factura = cursor.fetchone()[0]

                for linea in cotizacion["lineas"]:
                    cursor.execute("""
                        INSERT INTO factura_detalle (
                            id_factura, linea, concepto, id_tramo,
                            medio_transporte, descripcion, importe
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """, (
                        id_factura, linea["linea"], linea["concepto"],
                        linea["id_tramo"], linea["medio_transporte"],
                        linea["descripcion"], linea["importe"],
                    ))

                cursor.execute("""
                    UPDATE cuenta_corriente
                    SET saldo = saldo + %s,
                        fecha_actualizacion = CURRENT_TIMESTAMP
                    WHERE id_cliente = %s
                """, (cotizacion["total"], id_cliente))
                if cursor.rowcount != 1:
                    raise ValueError("No se pudo actualizar la cuenta corriente.")

                # Movimiento por el total con IVA: es lo que el cliente debe.
                cursor.execute("""
                    INSERT INTO movimiento_cuenta_corriente (
                        id_cliente, moneda, tipo_movimiento, importe_firmado,
                        fecha_contable, tipo_origen, referencia_origen,
                        referencia_documental
                    )
                    VALUES (%s, %s, 'FACTURA', %s, %s, 'FACTURA', %s, %s)
                """, (
                    id_cliente, moneda, cotizacion["total"], fecha_emision,
                    str(id_factura),
                    f"envio={id_envio};regla={regla['id_regla']};{origen.lower()}",
                ))

                return {
                    "id_factura": id_factura,
                    "id_envio": id_envio,
                    "id_cliente": id_cliente,
                    "fecha_emision": fecha_emision,
                    "neto": cotizacion["neto"],
                    "iva": cotizacion["iva"],
                    "total": cotizacion["total"],
                    "lineas": cotizacion["lineas"],
                }
    except errors.UniqueViolation:
        # Otro proceso facturó el mismo envío en paralelo.
        raise FacturaExistente("El envío ya fue facturado.") from None


def listar_envios_facturables(fecha_corte=None, id_cliente=None):
    """Envíos Entregados sin factura, con entrega hasta la fecha de corte
    (día argentino). Columnas: id_envio, id_cliente, cliente, origen,
    destino, fecha_entrega, cantidad de tramos."""
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT e.id_envio, e.id_cliente, c.razon_social,
                       e.origen, e.destino, e.fecha_entrega,
                       (SELECT COUNT(*) FROM tramo t
                        WHERE t.id_envio = e.id_envio) AS tramos
                FROM envio e
                JOIN cliente c ON c.id_cliente = e.id_cliente
                WHERE LOWER(BTRIM(e.estado)) = 'entregado'
                  AND e.fecha_entrega IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1 FROM factura f WHERE f.id_envio = e.id_envio
                  )
                  AND (%s::date IS NULL
                       OR (e.fecha_entrega AT TIME ZONE %s)::date <= %s::date)
                  AND (%s::bigint IS NULL OR e.id_cliente = %s::bigint)
                ORDER BY e.fecha_entrega, e.id_envio
            """, (fecha_corte, ZONA_CONTABLE, fecha_corte, id_cliente, id_cliente))
            return cursor.fetchall()


def obtener_detalle_factura(id_factura):
    """Encabezado y líneas de una factura, o None."""
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT f.id_factura, f.id_cliente, c.razon_social,
                       f.fecha_emision, f.id_envio, f.id_reporte,
                       f.importe_base, f.importe_impuestos,
                       f.tasa_impositiva, f.total, f.estado,
                       f.origen_emision, f.id_regla, f.fecha_entrega,
                       f.moneda
                FROM factura f
                JOIN cliente c ON c.id_cliente = f.id_cliente
                WHERE f.id_factura = %s
            """, (id_factura,))
            encabezado = cursor.fetchone()
            if encabezado is None:
                return None
            cursor.execute("""
                SELECT linea, concepto, id_tramo, medio_transporte,
                       descripcion, importe
                FROM factura_detalle
                WHERE id_factura = %s
                ORDER BY linea
            """, (id_factura,))
            lineas = cursor.fetchall()

    claves = ("id_factura", "id_cliente", "cliente", "fecha_emision",
              "id_envio", "id_reporte", "neto", "iva", "tasa_iva", "total",
              "estado", "origen_emision", "id_regla", "fecha_entrega", "moneda")
    return {**dict(zip(claves, encabezado)), "lineas": lineas}


def estado_facturacion_entregados():
    """Envíos Entregados: factura al cliente y facturas de operadores.

    Columnas: id_envio, cliente, fecha_entrega, id_factura, total factura,
    tramos, tramos con operador, tramos facturados por su operador.
    """
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT e.id_envio, c.razon_social, e.fecha_entrega,
                       f.id_factura, f.total,
                       (SELECT COUNT(*) FROM tramo t
                        WHERE t.id_envio = e.id_envio) AS tramos,
                       (SELECT COUNT(*) FROM tramo t
                        WHERE t.id_envio = e.id_envio
                          AND t.id_operador IS NOT NULL) AS con_operador,
                       (SELECT COUNT(*) FROM tramo t
                        JOIN factura_recibida fr
                          ON fr.id_tramo = t.id_tramo AND fr.estado <> 'Anulada'
                        WHERE t.id_envio = e.id_envio) AS facturados_operador
                FROM envio e
                JOIN cliente c ON c.id_cliente = e.id_cliente
                LEFT JOIN factura f ON f.id_envio = e.id_envio
                WHERE LOWER(BTRIM(e.estado)) = 'entregado'
                ORDER BY e.fecha_entrega DESC, e.id_envio
            """)
            return cursor.fetchall()


def reporte_facturacion_clientes():
    """Columnas 0-4 como antes; 5 facturado por envío, 6 facturado
    histórico (sin envío ni reporte)."""
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            # Agregación previa para no duplicar totales con varios pagos.
            cursor.execute("""
                WITH facturado AS (
                    SELECT id_cliente,
                           COUNT(*) AS cantidad,
                           SUM(total) AS total,
                           SUM(total) FILTER (WHERE id_envio IS NOT NULL)
                               AS por_envio,
                           SUM(total) FILTER (
                               WHERE id_envio IS NULL AND id_reporte IS NULL
                           ) AS historico
                    FROM factura
                    WHERE LOWER(TRIM(estado)) <> 'anulada'
                    GROUP BY id_cliente
                ),
                cobrado AS (
                    SELECT f.id_cliente, SUM(p.monto) AS total
                    FROM pago p
                    JOIN factura f ON f.id_factura = p.id_factura
                    GROUP BY f.id_cliente
                )
                SELECT c.id_cliente, c.razon_social,
                       COALESCE(fa.cantidad, 0) AS cantidad_facturas,
                       COALESCE(fa.total, 0) AS facturado,
                       COALESCE(co.total, 0) AS cobrado,
                       COALESCE(fa.por_envio, 0) AS facturado_por_envio,
                       COALESCE(fa.historico, 0) AS facturado_historico
                FROM cliente c
                LEFT JOIN facturado fa ON fa.id_cliente = c.id_cliente
                LEFT JOIN cobrado co ON co.id_cliente = c.id_cliente
                ORDER BY facturado DESC, c.razon_social
            """)
            return cursor.fetchall()


def emitir_factura_reporte(id_reporte):
    """Factura un reporte GENERADO (una factura por reporte).

    En una transacción: factura (origen REPORTE) + detalle + saldo + movimiento
    FACTURA por el total con IVA, y el reporte pasa a FACTURADO.
    """
    try:
        with get_postgres_connection() as conexion:
            with conexion.cursor() as cursor:
                cursor.execute("""
                    SELECT r.id_cliente, r.estado, r.importe_base, r.tipo,
                           c.estado,
                           (CURRENT_TIMESTAMP AT TIME ZONE %s)::date
                    FROM reporte r
                    JOIN cliente c ON c.id_cliente = r.id_cliente
                    WHERE r.id_reporte = %s
                    FOR UPDATE OF r, c
                """, (ZONA_CONTABLE, id_reporte))
                fila = cursor.fetchone()
                if fila is None:
                    raise ValueError("El reporte no existe.")
                id_cliente, estado, neto, tipo, estado_cliente, fecha_emision = fila

                cursor.execute(
                    "SELECT id_factura FROM factura WHERE id_reporte = %s",
                    (id_reporte,),
                )
                existente = cursor.fetchone()
                if existente is not None or estado == "FACTURADO":
                    raise FacturaExistente(
                        f"El reporte ya tiene la factura {existente[0] if existente else ''}."
                    )
                if estado != "GENERADO":
                    raise ValueError(
                        f"Solo se factura un reporte GENERADO (estado: {estado})."
                    )
                if str(estado_cliente).strip().upper() != "ACTIVO":
                    raise ValueError("El cliente no está activo.")

                neto = Decimal(neto).quantize(Decimal("0.01"))
                iva = calcular_iva(neto)
                total = neto + iva
                moneda = _obtener_moneda_cuenta_para_factura(cursor, id_cliente)
                if moneda != MONEDA_PROYECTO:
                    raise ValueError("La cuenta corriente del cliente no está en ARS.")

                cursor.execute("""
                    INSERT INTO factura (
                        id_cliente, fecha_emision, total, estado,
                        origen_emision, moneda, id_reporte,
                        importe_base, importe_impuestos, tasa_impositiva,
                        tratamiento_impositivo
                    )
                    VALUES (%s, %s, %s, 'Pendiente', 'REPORTE', %s, %s,
                            %s, %s, %s, %s)
                    RETURNING id_factura
                """, (
                    id_cliente, fecha_emision, total, moneda, id_reporte,
                    neto, iva, TASA_IVA, TRATAMIENTO_IVA,
                ))
                id_factura = cursor.fetchone()[0]

                cursor.execute("""
                    INSERT INTO factura_detalle (
                        id_factura, linea, concepto, id_tramo,
                        medio_transporte, descripcion, importe
                    )
                    VALUES (%s, 1, 'REPORTE', NULL, NULL, %s, %s)
                """, (id_factura, f"Reporte {id_reporte}: {tipo}", neto))

                cursor.execute("""
                    UPDATE cuenta_corriente
                    SET saldo = saldo + %s,
                        fecha_actualizacion = CURRENT_TIMESTAMP
                    WHERE id_cliente = %s
                """, (total, id_cliente))
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
                    id_cliente, moneda, total, fecha_emision, str(id_factura),
                    f"reporte={id_reporte};tipo={tipo}",
                ))

                cursor.execute("""
                    UPDATE reporte SET estado = 'FACTURADO'
                    WHERE id_reporte = %s AND estado = 'GENERADO'
                """, (id_reporte,))
                if cursor.rowcount != 1:
                    raise ValueError("No se pudo marcar el reporte como facturado.")

                return {"id_factura": id_factura, "id_reporte": id_reporte,
                        "neto": neto, "iva": iva, "total": total,
                        "fecha_emision": fecha_emision}
    except errors.UniqueViolation:
        raise FacturaExistente("El reporte ya fue facturado.") from None
