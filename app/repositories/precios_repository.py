"""Tarifa estándar de transporte sobre el motor de reglas existente.

Una versión de TARIFA_ESTANDAR tiene un cargo BASE por envío y un precio fijo
por tramo para cada medio. Definir precios crea una versión nueva y la aprueba
en la misma transacción (con la auditoría que exige la migración 008); la
versión anterior queda REEMPLAZADA y se conserva.
"""

from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.database.postgres_connection import get_postgres_connection
from app.services.cotizacion_envio import CODIGO_TARIFA, MONEDA
from app.utils.validaciones_logistica import MEDIOS_TRANSPORTE


ZONA = ZoneInfo("America/Argentina/Buenos_Aires")  # la vigencia de la tarifa se fecha en hora argentina


def obtener_tarifa_estandar():  # tarifa estándar aprobada con base y precio por medio; la usa "Precios de transporte" (facturación, opción 9)
    """Versión aprobada vigente con sus precios, o None si no hay."""
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT id_regla, version, vigente_desde, aprobado_en,
                       referencia_aprobacion
                FROM regla_tarifaria_version
                WHERE codigo = %s AND estado = 'APROBADA'  -- solo hay una versión aprobada a la vez
            """, (CODIGO_TARIFA,))
            regla = cursor.fetchone()
            if regla is None:
                return None
            cursor.execute("""
                SELECT criterio, selector, importe
                FROM regla_tarifaria_componente
                WHERE id_regla = %s
                ORDER BY criterio, selector
            """, (regla[0],))
            componentes = cursor.fetchall()

    precios = {}
    base = None
    for criterio, selector, importe in componentes:  # separa el cargo base de los precios por medio
        if criterio == "BASE":
            base = importe
        elif criterio == "TRANSPORTE":
            precios[selector] = importe
    return {
        "id_regla": regla[0],
        "version": regla[1],
        "vigente_desde": regla[2],
        "aprobado_en": regla[3],
        "referencia": regla[4],
        "base": base,
        "precios": precios,
    }


def validar_precios(base, precios):  # controla los importes de la tarifa; la usa definir_tarifa_estandar
    """Base >= 0 y precio > 0 para cada uno de los tres medios, en centavos."""
    def _importe(valor, nombre, minimo_exclusivo):
        try:
            numero = Decimal(str(valor))
        except Exception:
            raise ValueError(f"{nombre}: importe inválido.") from None
        if not numero.is_finite() or numero != numero.quantize(Decimal("0.01")):
            raise ValueError(f"{nombre}: usá un importe con hasta 2 decimales.")
        if numero < 0 or (minimo_exclusivo and numero == 0):
            raise ValueError(
                f"{nombre}: debe ser mayor a cero."
                if minimo_exclusivo else f"{nombre}: no puede ser negativo."
            )
        from app.utils.validaciones_datos import controlar_maximo
        return controlar_maximo(numero, nombre)

    base = _importe(base, "Cargo base", False)
    resultado = {}
    for medio in MEDIOS_TRANSPORTE:  # tiene que haber precio para cada medio
        if medio not in (precios or {}):
            raise ValueError(f"Falta el precio por tramo {medio}.")
        resultado[medio] = _importe(precios[medio], f"Tramo {medio}", True)
    return base, resultado


def definir_tarifa_estandar(base, precios, usuario_id, referencia):  # crea y aprueba una versión nueva de la tarifa; la usa la opción 9 de facturación
    """Crea y aprueba una nueva versión de TARIFA_ESTANDAR. Devuelve id_regla."""
    base, precios = validar_precios(base, precios)
    referencia = str(referencia or "").strip()
    if not referencia:
        raise ValueError("Indicá una referencia documentada del cambio de precios.")
    if not usuario_id:
        raise ValueError("No hay un usuario autenticado.")

    hoy = datetime.now(ZONA).date()

    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            # Serializa cambios de precio concurrentes del mismo código.
            cursor.execute(  # candado: dos cambios de precio a la vez no se pisan
                "SELECT pg_advisory_xact_lock(hashtext(%s))", (CODIGO_TARIFA,)
            )
            cursor.execute("""
                SELECT COALESCE(MAX(version), 0) + 1  -- número de versión siguiente
                FROM regla_tarifaria_version WHERE codigo = %s
            """, (CODIGO_TARIFA,))
            version = cursor.fetchone()[0]

            cursor.execute("""
                INSERT INTO regla_tarifaria_version
                    (codigo, version, moneda, vigente_desde, vigente_hasta,
                     creada_por)
                VALUES (%s, %s, %s, %s, NULL, %s)
                RETURNING id_regla
            """, (CODIGO_TARIFA, version, MONEDA, hoy, usuario_id))
            id_regla = cursor.fetchone()[0]

            componentes = [("BASE", None, "ENVIO", "FIJO", base)] + [  # un cargo base por envío y un precio fijo por tramo para cada medio
                ("TRANSPORTE", medio, "TRAMO", "FIJO", importe)
                for medio, importe in precios.items()
            ]
            for criterio, selector, ambito, base_calculo, importe in componentes:
                cursor.execute("""
                    INSERT INTO regla_tarifaria_componente
                        (id_regla, criterio, selector, ambito, base_calculo,
                         importe)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (id_regla, criterio, selector, ambito, base_calculo, importe))

            cursor.execute("""
                SELECT id_regla FROM regla_tarifaria_version
                WHERE codigo = %s AND estado = 'APROBADA'
                FOR UPDATE  -- bloquea la versión aprobada anterior
            """, (CODIGO_TARIFA,))
            anterior = cursor.fetchone()
            if anterior is not None:  # la anterior pasa a REEMPLAZADA y se conserva, con auditoría
                cursor.execute("""
                    INSERT INTO regla_tarifaria_auditoria
                        (id_regla, estado_anterior, estado_nuevo, motivo,
                         usuario_id, id_transaccion)
                    VALUES (%s, 'APROBADA', 'REEMPLAZADA', %s, %s, txid_current())
                """, (anterior[0], f"Reemplazada por versión {version}", usuario_id))
                cursor.execute("""
                    UPDATE regla_tarifaria_version SET estado = 'REEMPLAZADA'
                    WHERE id_regla = %s
                """, (anterior[0],))

            cursor.execute("""
                INSERT INTO regla_tarifaria_auditoria
                    (id_regla, estado_anterior, estado_nuevo, motivo,
                     usuario_id, id_transaccion)
                VALUES (%s, 'BORRADOR', 'APROBADA', %s, %s, txid_current())  -- auditoría del paso de BORRADOR a APROBADA
            """, (id_regla, referencia, usuario_id))
            cursor.execute("""
                UPDATE regla_tarifaria_version
                SET estado = 'APROBADA', referencia_aprobacion = %s,  -- la versión nueva queda APROBADA y es la que se factura
                    aprobado_por = %s, aprobado_en = CURRENT_TIMESTAMP
                WHERE id_regla = %s
            """, (referencia, usuario_id, id_regla))

            return id_regla
