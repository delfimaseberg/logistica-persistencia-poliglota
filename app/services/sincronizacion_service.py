from app.repositories.evento_repository import (
    registrar_pendiente_sync,
    listar_pendientes,
    resolver_pendientes_envio
)
from app.repositories.grafo_repository import (
    sincronizar_envio_grafo,
    eliminar_envio_grafo,
    eliminar_operadores_legados
)
from app.repositories.trazabilidad_repository import (
    obtener_datos_proyeccion,
    listar_ids_envios
)
from app.utils.errores import mensaje_error
from app.utils.logger import obtener_logger


logger = obtener_logger("sincronizacion")


def reconciliar_envio(id_envio):
    """Deja Neo4j igual a PostgreSQL para un envío.

    Si el envío existe en PostgreSQL lo proyecta; si no existe, lo
    elimina del grafo. Lanza excepción si falla.
    """
    datos = obtener_datos_proyeccion(id_envio)

    if datos is None:
        eliminar_envio_grafo(id_envio)
    else:
        sincronizar_envio_grafo(datos)


def _marcar_pendiente(id_envio, error):
    logger.error(
        "Fallo la sincronización con Neo4j del envío %s: %s",
        id_envio, error
    )

    try:
        registrar_pendiente_sync(id_envio, error)
        return True
    except Exception as error_mongo:
        logger.error(
            "No se pudo registrar el pendiente del envío %s: %s",
            id_envio, error_mongo
        )
        return False


def sincronizar_envio_neo4j(id_envio):
    """Proyecta el envío en Neo4j sin interrumpir la operación principal.

    PostgreSQL ya confirmó el cambio. Si Neo4j falla, el error se guarda
    como pendiente (persistente) para repararlo desde el menú de
    trazabilidad. Nunca lanza excepciones. Devuelve True si sincronizó.
    """
    try:
        reconciliar_envio(id_envio)
    except Exception as error:
        guardado = _marcar_pendiente(id_envio, error)
        if guardado:
            print("\nAdvertencia: la red de rutas no está disponible; la actualización quedó pendiente.")
        else:
            print("\nADVERTENCIA: no se pudo actualizar la red de rutas ni guardar el pendiente. El detalle quedó registrado para revisión.")
        return False

    try:
        resolver_pendientes_envio(id_envio)
    except Exception as error:
        logger.warning(
            "No se pudieron cerrar los pendientes del envío %s: %s",
            id_envio, error
        )

    logger.info("Envío %s sincronizado con Neo4j", id_envio)
    return True


# Misma lógica: reconcilia según exista o no en PostgreSQL.


def reparar_pendientes():
    """Reintenta los pendientes guardados. Devuelve (resueltos, fallidos)."""
    resueltos = 0
    fallidos = []

    for pendiente in listar_pendientes():
        id_envio = pendiente["envio_id"]

        try:
            reconciliar_envio(id_envio)
            resolver_pendientes_envio(id_envio)
            resueltos += 1
            logger.info("Pendiente del envío %s reparado", id_envio)
        except Exception as error:
            registrar_pendiente_sync(id_envio, error)
            fallidos.append((id_envio, mensaje_error(error)))
            logger.error(
                "Reintento fallido del envío %s: %s", id_envio, error
            )

    return resueltos, fallidos


def resincronizar_envio(id_envio):
    """Igual que resincronizar_todos, para un solo envío.

    Devuelve None si quedó sincronizado o el motivo del error (texto para
    mostrar); en ese caso queda como pendiente para reintentar.
    """
    try:
        reconciliar_envio(id_envio)
        resolver_pendientes_envio(id_envio)
    except Exception as error:
        _marcar_pendiente(id_envio, error)
        logger.error("Resincronización fallida del envío %s: %s", id_envio, error)
        return mensaje_error(error)
    logger.info("Envío %s resincronizado con Neo4j", id_envio)
    return None


def resincronizar_todos():
    """Reconstruye la proyección de todos los envíos desde PostgreSQL.

    Devuelve (cantidad_ok, lista_de_errores).
    """
    correctos = 0
    errores = []

    for id_envio in listar_ids_envios():
        try:
            reconciliar_envio(id_envio)
            resolver_pendientes_envio(id_envio)
            correctos += 1
        except Exception as error:
            errores.append((id_envio, mensaje_error(error)))
            _marcar_pendiente(id_envio, error)
            logger.error(
                "Resincronización fallida del envío %s: %s",
                id_envio, error
            )

    # Los :Operador viejos (creados desde el texto libre del vehículo, sin
    # id_operador) ya no tienen relaciones tras proyectar todos los envíos.
    # Solo se borran si todos los envíos se proyectaron bien.
    if not errores:
        try:
            eliminados = eliminar_operadores_legados()
            if eliminados:
                logger.info(
                    "Operadores legados eliminados de Neo4j: %s", eliminados
                )
        except Exception as error:
            errores.append(("operadores_legados", mensaje_error(error)))
            logger.error("No se pudieron limpiar operadores legados: %s", error)

    return correctos, errores
