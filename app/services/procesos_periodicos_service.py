
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.repositories.sensor_repository import listar_sensores
from app.repositories.lectura_iot_repository import (
    consultar_ultima_lectura_db,
)
from app.repositories.alerta_repository import registrar_alerta
from app.services.predicciones_service import (
    actualizar_predicciones_activas,
)
from app.utils.logger import obtener_logger


logger = obtener_logger("procesos_periodicos")
ZONA_ARGENTINA = ZoneInfo("America/Argentina/Buenos_Aires")

PROCESOS_DISPONIBLES = {"predicciones", "sensores"}


def detectar_sensores_inactivos_automatico(horas=24, ahora=None):
    """
    Detecta sensores activos sin lecturas recientes y registra
    alertas en MongoDB.

    No cambia el estado del sensor ni crea incidentes sin un
    envío asociado.
    """
    if not 0 < horas <= 8760:
        raise ValueError(
            "Las horas deben ser mayores a 0 y menores o iguales a 8760."
        )

    ahora = ahora or datetime.now(timezone.utc)

    if ahora.tzinfo is None:
        raise ValueError("La fecha debe incluir zona horaria.")

    limite = ahora - timedelta(hours=horas)

    resumen = {
        "fecha_ejecucion": ahora,
        "horas_limite": horas,
        "sensores_activos": 0,
        "al_dia": 0,
        "sin_lecturas": [],
        "atrasados": [],
        "alertas_procesadas": 0,
        "errores": [],
    }

    sensores = listar_sensores()

    for sensor in sensores:
        id_sensor = sensor[0]
        id_contenedor = sensor[1]
        estado = str(sensor[6]).strip().lower()

        if estado != "activo":
            continue

        resumen["sensores_activos"] += 1

        try:
            lectura = consultar_ultima_lectura_db(id_sensor)

            if lectura is None:
                resumen["sin_lecturas"].append(id_sensor)
                tipo = "Sensor sin lecturas registradas"
                descripcion = (
                    f"El sensor {id_sensor} del contenedor "
                    f"{id_contenedor} no tiene lecturas registradas."
                )

            else:
                fecha = lectura.fecha_hora

                if fecha.tzinfo is None:
                    fecha = fecha.replace(tzinfo=timezone.utc)

                if fecha >= limite:
                    resumen["al_dia"] += 1
                    continue

                resumen["atrasados"].append({
                    "sensor_id": id_sensor,
                    "ultima_lectura": fecha,
                })

                tipo = "Sensor sin transmisión reciente"
                descripcion = (
                    f"El sensor {id_sensor} del contenedor "
                    f"{id_contenedor} no transmite desde "
                    f"{fecha.isoformat()}. Umbral: {horas} horas."
                )

            # Una alerta por sensor, tipo y día evita duplicados
            # si el proceso se ejecuta varias veces durante el día.
            dia_deteccion = ahora.astimezone(
                ZONA_ARGENTINA
            ).date().isoformat()
            clave = f"{id_sensor}:{tipo}:{dia_deteccion}"

            registrar_alerta(
                sensor_id=id_sensor,
                contenedor_id=id_contenedor,
                tipo=tipo,
                severidad="Media",
                descripcion=descripcion,
                clave_deteccion=clave,
            )

            resumen["alertas_procesadas"] += 1

            logger.warning(
                "Alerta de sensor procesada: sensor=%s, tipo=%s",
                id_sensor,
                tipo,
            )

        except Exception as error:
            resumen["errores"].append({
                "sensor_id": id_sensor,
                "error": str(error),
            })

            logger.exception(
                "Error al revisar el sensor %s",
                id_sensor,
            )

    logger.info(
        "Revisión IoT terminada: activos=%s, al_dia=%s, "
        "sin_lecturas=%s, atrasados=%s, alertas=%s, errores=%s",
        resumen["sensores_activos"],
        resumen["al_dia"],
        len(resumen["sin_lecturas"]),
        len(resumen["atrasados"]),
        resumen["alertas_procesadas"],
        len(resumen["errores"]),
    )

    return resumen


def ejecutar_predicciones_diarias():
    """Actualiza las predicciones de riesgo."""
    logger.info("Iniciando predicciones diarias")

    resultado = actualizar_predicciones_activas()

    logger.info(
        "Predicciones finalizadas: guardadas=%s, "
        "riesgos_altos=%s, errores=%s",
        resultado["guardadas"],
        resultado["riesgos_altos"],
        resultado["errores"],
    )

    return resultado


def ejecutar_revision_sensores(horas=24):
    """Ejecuta la revisión periódica de sensores."""
    logger.info(
        "Iniciando revisión de sensores. Umbral: %s horas",
        horas,
    )

    return detectar_sensores_inactivos_automatico(horas=horas)


def ejecutar_todos_los_procesos(horas_sensores=24, procesos=None):
    """
    Ejecuta los procesos disponibles de forma independiente.
    Si uno falla, intenta ejecutar el siguiente.

    ``procesos`` permite seleccionar trabajos para el Programador de
    tareas. Por defecto conserva el comportamiento anterior: ejecutar
    predicciones y sensores.
    """
    if procesos is None:
        procesos = ("predicciones", "sensores")
    else:
        procesos = tuple(dict.fromkeys(procesos))

    desconocidos = set(procesos) - PROCESOS_DISPONIBLES
    if desconocidos:
        raise ValueError(
            "Procesos desconocidos: " + ", ".join(sorted(desconocidos))
        )

    if not procesos:
        raise ValueError("Debe seleccionarse al menos un proceso.")

    resultado = {
        "fecha_ejecucion": datetime.now(timezone.utc),
        "predicciones": None,
        "sensores": None,
        "errores": {},
    }

    for proceso in procesos:
        try:
            if proceso == "predicciones":
                resultado[proceso] = ejecutar_predicciones_diarias()
            else:
                resultado[proceso] = ejecutar_revision_sensores(
                    horas=horas_sensores,
                )
        except Exception as error:
            resultado["errores"][proceso] = str(error)
            logger.exception(
                "Falló el proceso periódico de %s",
                proceso,
            )

    return resultado
