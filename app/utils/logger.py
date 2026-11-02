import logging
import os
from logging.handlers import RotatingFileHandler

DIRECTORIO_LOGS = "logs"
ARCHIVO_LOG = "app.log"

_configurado = False


def obtener_logger(nombre):
    """Devuelve un logger que escribe en logs/app.log.

    Los mensajes no se muestran por consola para no ensuciar los menús.
    """
    global _configurado

    raiz = logging.getLogger("logistica")

    if not _configurado:
        # LOGS_DIR permite separar los logs (los tests escriben en una
        # carpeta temporal y no en el log real de la aplicación).
        directorio = os.getenv("LOGS_DIR", DIRECTORIO_LOGS)
        os.makedirs(directorio, exist_ok=True)

        manejador = RotatingFileHandler(
            os.path.join(directorio, ARCHIVO_LOG),
            maxBytes=1_000_000,
            backupCount=3,
            encoding="utf-8"
        )
        manejador.setFormatter(logging.Formatter(
            "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
        ))

        raiz.addHandler(manejador)
        raiz.setLevel(logging.INFO)
        raiz.propagate = False
        _configurado = True

    return raiz.getChild(nombre)
