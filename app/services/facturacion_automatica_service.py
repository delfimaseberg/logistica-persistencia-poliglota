"""Facturación automática: una factura por cada envío Entregado sin factura.

Proceso periódico (menú de facturación y ejecutar_procesos.py --job
facturacion). Idempotente: un envío ya facturado no vuelve a facturarse
(consulta previa + índice único uq_factura_original_envio). Cada envío se
emite en su propia transacción, así un error no frena al resto.
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.repositories.facturacion_repository import (
    FacturaExistente,
    emitir_factura_envio,
    listar_envios_facturables,
    registrar_auditoria_facturacion,
)
from app.services.cotizacion_envio import CotizacionImposible
from app.utils.errores import mensaje_error
from app.utils.logger import obtener_logger


ZONA_ARGENTINA = ZoneInfo("America/Argentina/Buenos_Aires")
logger = obtener_logger("facturacion_automatica")


def hoy_argentina():
    return datetime.now(ZONA_ARGENTINA).date()


def _auditar(id_envio, resultado, motivo, id_factura=None):
    try:
        registrar_auditoria_facturacion(
            id_envio=id_envio,
            envio_id_reportado=id_envio,
            evento_entrega_id=None,
            resultado=resultado,
            motivo=motivo,
            id_factura=id_factura,
        )
    except Exception:
        logger.exception("No se pudo auditar la facturación del envío %s", id_envio)


def procesar_facturacion_automatica(fecha_corte=None):
    """Factura los envíos Entregados sin factura con entrega <= fecha_corte.

    Devuelve un resumen con facturados, omitidos (con motivo) y errores.
    """
    fecha_corte = fecha_corte or hoy_argentina()
    if not isinstance(fecha_corte, date) or isinstance(fecha_corte, datetime):
        raise ValueError("La fecha de corte debe ser una fecha calendario.")

    resumen = {
        "fecha_corte": fecha_corte,
        "candidatos": 0,
        "facturados": [],
        "omitidos": [],
        "errores": [],
    }

    candidatos = listar_envios_facturables(fecha_corte=fecha_corte)
    resumen["candidatos"] = len(candidatos)
    logger.info(
        "Facturación automática: corte=%s candidatos=%s",
        fecha_corte, len(candidatos),
    )

    for fila in candidatos:
        id_envio, cliente = fila[0], fila[2]
        try:
            factura = emitir_factura_envio(id_envio, origen="ENVIO_AUTOMATICA")
            resumen["facturados"].append({
                "id_envio": id_envio,
                "cliente": cliente,
                "id_factura": factura["id_factura"],
                "total": factura["total"],
            })
            _auditar(id_envio, "FACTURADA", "Factura por envío emitida.",
                     factura["id_factura"])
        except FacturaExistente as error:
            # Otro proceso lo facturó entre la consulta y la emisión.
            resumen["omitidos"].append({
                "id_envio": id_envio, "cliente": cliente, "motivo": mensaje_error(error),
            })
        except CotizacionImposible as error:
            motivo = mensaje_error(error)
            resumen["omitidos"].append({
                "id_envio": id_envio, "cliente": cliente, "motivo": motivo,
            })
            _auditar(id_envio, "BLOQUEADA", motivo)
        except ValueError as error:
            motivo = mensaje_error(error)
            resumen["omitidos"].append({
                "id_envio": id_envio, "cliente": cliente, "motivo": motivo,
            })
            _auditar(id_envio, "BLOQUEADA", motivo)
        except Exception as error:
            logger.exception("Error al facturar el envío %s", id_envio)
            resumen["errores"].append({
                "id_envio": id_envio, "cliente": cliente, "error": mensaje_error(error),
            })
            _auditar(id_envio, "ERROR", f"ERROR: {mensaje_error(error)}")

    logger.info(
        "Facturación automática terminada: facturados=%s omitidos=%s errores=%s",
        len(resumen["facturados"]), len(resumen["omitidos"]),
        len(resumen["errores"]),
    )
    return resumen
