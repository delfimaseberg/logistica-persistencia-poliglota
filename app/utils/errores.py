"""Mensajes claros para el usuario a partir de cualquier excepción.

Los errores de validación de la aplicación (ValueError, PermissionError,
LookupError) ya traen un texto pensado para el usuario y se muestran tal cual.
Los errores de las bases de datos se traducen; el detalle técnico queda en
logs/app.log.
"""

import re

from app.utils.logger import obtener_logger


logger = obtener_logger("errores")

# Tabla que referencia al registro -> qué se le dice al usuario.
DEPENDENCIAS = {
    "apertura_cuenta_corriente": "una cuenta corriente abierta",
    "cuenta_corriente": "una cuenta corriente",
    "movimiento_cuenta_corriente": "movimientos en su cuenta corriente",
    "cierre_cuenta_corriente": "cierres de cuenta corriente",
    "factura": "facturas",
    "factura_detalle": "facturas",
    "factura_recibida": "facturas recibidas",
    "pago": "pagos",
    "pago_emitido": "pagos emitidos",
    "envio": "envíos",
    "envio_carga": "partidas de carga",
    "envio_contenedor": "contenedores asociados",
    "tramo": "tramos",
    "incidente": "incidentes",
    "reporte": "reportes",
    "usuario": "usuarios",
    "sesion": "sesiones registradas",
    "sensor_iot": "sensores",
    "vehiculo": "vehículos",
    "regla_alerta": "reglas de alerta",
    "tipo_reporte": "precios de reportes",
    "cuenta_corriente_tercero": "una cuenta corriente",
    "movimiento_cuenta_tercero": "movimientos en su cuenta corriente",
}


def _psycopg(error):
    try:
        import psycopg.errors as pe
    except ImportError:  # pragma: no cover
        return None
    if isinstance(error, pe.ForeignKeyViolation):
        tabla = getattr(getattr(error, "diag", None), "table_name", None)
        detalle = DEPENDENCIAS.get(tabla, "otros datos")
        texto = str(error)
        if "update o delete" in texto or "update or delete" in texto:
            return (f"No se puede eliminar porque tiene {detalle} asociados. "
                    "Si ya no se usa, podés darlo de baja (estado inactivo).")
        return "Alguno de los datos indicados no existe."
    if isinstance(error, pe.UniqueViolation):
        return "Ya existe un registro con esos datos."
    if isinstance(error, pe.NotNullViolation):
        return "Falta un dato obligatorio."
    if isinstance(error, (pe.CheckViolation, pe.RaiseException)):
        # Los triggers y CHECK de las migraciones traen un texto propio;
        # se muestra solo la primera línea, sin nombres internos.
        primera = str(error).splitlines()[0]
        if ("viola la restricción" in primera or "violates check" in primera
                or _TECNICO.search(primera)):
            return "Los datos no cumplen las reglas del sistema."
        return primera
    if isinstance(error, pe.ReadOnlySqlTransaction):
        return "La base de datos está en modo de solo lectura; no se guardaron cambios."
    import psycopg
    if isinstance(error, psycopg.OperationalError):
        return "No se pudo conectar con la base de datos. Intentá nuevamente en unos minutos."
    if isinstance(error, psycopg.Error):
        return "No se pudo completar la operación en la base de datos."
    return None


def _servicios_externos(error):
    nombre = type(error).__module__ or ""
    if nombre.startswith(("pymongo", "bson")):
        return "El servicio de eventos, alertas y mensajes no está disponible en este momento."
    if nombre.startswith("cassandra"):
        return "El servicio de lecturas de sensores no está disponible en este momento."
    if nombre.startswith("neo4j"):
        return "El servicio de la red de rutas no está disponible en este momento."
    return None


# Señales de un texto técnico (de Python, del sistema o de una librería):
# nunca se muestra al usuario aunque venga en un ValueError o RuntimeError.
_TECNICO = re.compile(
    r"Traceback|Errno|\bNone(Type)?\b|\bobject\b|\battribute\b|\bargument\b|"
    r"invalid literal|could not|isoformat|codec|base 10|unconverted|does not match|"
    r"time data|math domain|unpack|\bexpected\b|\bunexpected\b|out of range|"
    r"not in list|not found|not supported|maximum recursion|changed size|generator|"
    r"psycopg|pymongo|bson|neo4j|cassandra|\b(SELECT|INSERT|relation|column|constraint|"
    r"violates|syntax)\b|\b(the|is|are|of|for|with|must|cannot|can't|invalid|unknown|not)\b|"
    r"[A-Za-z]:\\|/[A-Za-z_]+/|<[\w.]+ object|\w\(\)|\w+Error\b",
    re.IGNORECASE,
)
GENERICO = "Ocurrió un error inesperado. El detalle quedó registrado para revisión."


def _texto_de_la_aplicacion(error):
    """El texto del error si lo escribió la aplicación para el usuario, o None."""
    clase = type(error)
    propia = clase.__module__.startswith("app.")
    validacion = (clase.__module__ == "builtins"
                  and isinstance(error, (ValueError, PermissionError, LookupError, RuntimeError))
                  and not isinstance(error, (KeyError, IndexError, UnicodeError, RecursionError,
                                             NotImplementedError))
                  and getattr(error, "errno", None) is None)   # OSError del sistema: no
    if not (propia or validacion):
        return None
    texto = str(error).strip()
    if not texto or _TECNICO.search(texto):
        return None
    return texto


def mensaje_error(error):
    """Texto para mostrar al usuario. Nunca devuelve detalles técnicos.

    El detalle técnico (tipo, texto original y traza) queda solo en el log.
    """
    texto = _texto_de_la_aplicacion(error)
    if texto is not None:
        return texto
    for traductor in (_psycopg, _servicios_externos):
        texto = traductor(error)
        if texto:
            logger.warning("Error mostrado al usuario como %r: %r", texto, error)
            return texto
    if isinstance(error, OSError):
        logger.error("Error de archivo mostrado al usuario: %r", error, exc_info=error)
        return "No se pudo acceder al archivo o a la carpeta indicada."
    logger.error("Error inesperado mostrado al usuario: %r", error, exc_info=error)
    return GENERICO
