"""Facturación automática validada, fuera del lanzador periódico."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.repositories.facturacion_repository import (
    contar_facturas_sin_envio_cliente,
    emitir_factura_automatica,
    existe_factura_original,
    obtener_contexto_tarifas_aprobadas,
    listar_envios_entregados_candidatos_facturacion,
    registrar_auditoria_facturacion,
)
from app.repositories.envio_repository import listar_envios
from app.repositories.evento_repository import (
    listar_eventos_entregados,
    listar_pendientes_estado,
)
from app.utils.logger import obtener_logger
from app.utils.validaciones_financieras import (
    FinanzasNoConfiguradas,
    validar_evento_entrega,
    validar_factura_original_no_duplicada,
    validar_tarifa_aprobada,
)


MOTIVOS_BLOQUEO = (
    "Falta una tarifa aprobada con importe, moneda y tratamiento fiscal válidos.",
    "La factura automática debe conservar referencias al envío y su evento de entrega.",
)
ZONA_ARGENTINA = ZoneInfo("America/Argentina/Buenos_Aires")
logger = obtener_logger("facturacion_automatica")
# No existe todavía una operación de la aplicación para cargar y aprobar
# tarifas, moneda y configuración fiscal. Mantener en False hasta incorporarla.
FACTURACION_AUTOMATICA_HABILITADA = False


def revisar_envios_potencialmente_facturables():
    """Devuelve envíos entregados como candidatos, sin emitir facturas."""
    filas = listar_envios_entregados_candidatos_facturacion()
    candidatos = [
        {
            "id_envio": fila[0],
            "id_cliente": fila[1],
            "estado": fila[2],
        }
        for fila in filas
    ]

    return {
        "candidatos": candidatos,
        "facturas_emitidas": 0,
        "bloqueado": True,
        "motivos": list(MOTIVOS_BLOQUEO),
    }


def _registrar_resultado(
    id_envio,
    envio_id_reportado,
    evento_id,
    resultado,
    motivo,
    id_factura=None,
):
    try:
        registrar_auditoria_facturacion(
            id_envio=id_envio,
            envio_id_reportado=envio_id_reportado,
            evento_entrega_id=evento_id,
            resultado=resultado,
            motivo=motivo,
            id_factura=id_factura,
        )
    except Exception:
        logger.exception(
            "No se pudo persistir la auditoría financiera del envío %s",
            envio_id_reportado,
        )


def procesar_facturacion_automatica(fecha_emision=None):
    """Emite facturas elegibles; nunca se invoca desde el lanzador aún.

    Cualquier inconsistencia o dependencia incompleta bloquea el envío y deja
    un registro de auditoría. La factura, el saldo, el ledger y la auditoría de
    éxito se escriben en una sola transacción PostgreSQL.
    """
    if fecha_emision is None:
        fecha_emision = datetime.now(ZONA_ARGENTINA).date()
    if not isinstance(fecha_emision, date) or isinstance(fecha_emision, datetime):
        raise ValueError("La fecha de emisión debe ser una fecha calendario.")

    resumen = {
        "candidatos": 0,
        "facturas_emitidas": 0,
        "bloqueadas": [],
        "errores": [],
        "facturas": [],
    }

    if not FACTURACION_AUTOMATICA_HABILITADA:
        motivo = (
            "Emisión automática deshabilitada: falta implementar y validar "
            "la operación de carga/aprobación de tarifas y configuración fiscal."
        )
        logger.warning(motivo)
        resumen["bloqueadas"].append({"envio_id": None, "motivo": motivo})
        return resumen

    try:
        filas_envio = listar_envios()
    except Exception as error:
        logger.exception("No se pudieron consultar los envíos en PostgreSQL")
        resumen["errores"].append({"error": str(error)})
        return resumen

    envios = {int(fila[0]): fila for fila in filas_envio}
    try:
        eventos = listar_eventos_entregados()
        pendientes = listar_pendientes_estado()
    except Exception as error:
        logger.exception("No se pudo consultar la evidencia de entrega en MongoDB")
        candidatos_pg = [
            envio_id for envio_id, fila in envios.items()
            if str(fila[5]).strip().casefold() == "entregado"
        ]
        for envio_id in candidatos_pg:
            resumen["candidatos"] += 1
            motivo = f"ERROR: no se pudo validar MongoDB: {error}"
            _registrar_resultado(
                envio_id, envio_id, None, "ERROR", motivo
            )
            resumen["errores"].append({"envio_id": envio_id, "error": motivo})
        return resumen

    eventos_por_envio = {}
    for evento in eventos:
        try:
            envio_id = int(evento["envio_id"])
        except (KeyError, TypeError, ValueError):
            logger.error("MongoDB contiene un evento ENTREGADO sin envio_id válido")
            continue
        eventos_por_envio.setdefault(envio_id, []).append(evento)

    pendientes_por_evento = {
        str(pendiente.get("evento_id"))
        for pendiente in pendientes
        if not pendiente.get("resuelto", False)
    }

    ids_candidatos = {
        envio_id for envio_id, fila in envios.items()
        if str(fila[5]).strip().casefold() == "entregado"
    }
    ids_candidatos.update(eventos_por_envio)

    for envio_id in sorted(ids_candidatos):
        resumen["candidatos"] += 1
        fila_envio = envios.get(envio_id)
        lista_eventos = eventos_por_envio.get(envio_id, [])
        evento = lista_eventos[0] if lista_eventos else None
        evento_id = evento.get("_id") if evento else None
        estado_pg = fila_envio[5] if fila_envio else None

        def bloquear(motivo, resultado="BLOQUEADA"):
            _registrar_resultado(
                envio_id if fila_envio else None,
                envio_id,
                evento_id,
                resultado,
                motivo,
            )
            destino = "errores" if resultado == "ERROR" else "bloqueadas"
            resumen[destino].append({"envio_id": envio_id, "motivo": motivo})

        if fila_envio is None:
            bloquear(
                "El evento ENTREGADO de MongoDB refiere a un envío inexistente "
                "en PostgreSQL.",
            )
            continue

        if evento_id and str(evento_id) in pendientes_por_evento:
            bloquear(
                "La sincronización de estado asociada al evento sigue pendiente."
            )
            continue

        try:
            evidencia = validar_evento_entrega(
                envio_id,
                evento,
                estado_pg,
                cantidad_eventos_entrega=len(lista_eventos),
            )
        except FinanzasNoConfiguradas as error:
            bloquear(str(error))
            continue

        try:
            contextos = obtener_contexto_tarifas_aprobadas(envio_id)
            if not contextos:
                raise FinanzasNoConfiguradas(
                    "No hay una tarifa aprobada asociada al envío."
                )
            if len(contextos) != 1:
                raise FinanzasNoConfiguradas(
                    "Hay más de una tarifa aprobada asociada al envío."
                )

            contexto = contextos[0]
            importes = validar_tarifa_aprobada(
                contexto["tarifa"],
                contexto["moneda_cuenta"],
                contexto["configuracion_fiscal"],
                fecha_emision,
            )
            if existe_factura_original(envio_id, evidencia["evento_id"]):
                validar_factura_original_no_duplicada(
                    existe_factura_envio=True
                )

            id_cliente = fila_envio[1]
            if contar_facturas_sin_envio_cliente(id_cliente):
                raise FinanzasNoConfiguradas(
                    "Hay facturas manuales sin vínculo a envío para este "
                    "cliente; conciliarlas antes de emitir automáticamente."
                )

            id_factura = emitir_factura_automatica(
                id_envio=envio_id,
                evento_entrega_id=evidencia["evento_id"],
                fecha_entrega=evidencia["fecha_hora"],
                fecha_emision=fecha_emision,
                id_tarifa=contexto["tarifa"]["id_tarifa"],
            )
            resumen["facturas_emitidas"] += 1
            resumen["facturas"].append({
                "envio_id": envio_id,
                "id_factura": id_factura,
                "importe_total": importes["importe_total"],
                "moneda": importes["moneda"],
            })
        except FinanzasNoConfiguradas as error:
            bloquear(str(error))
        except ValueError as error:
            # Incluye duplicados detectados de nuevo dentro de la transacción,
            # por ejemplo si otro proceso ganó la carrera de emisión.
            bloquear(str(error))
        except Exception as error:
            logger.exception(
                "Error al emitir factura automática para envío %s",
                envio_id,
            )
            motivo = f"ERROR: {error}"
            bloquear(motivo, resultado="ERROR")

    return resumen
