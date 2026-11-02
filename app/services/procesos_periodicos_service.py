
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.repositories.sensor_repository import listar_sensores
from app.repositories.lectura_iot_repository import (
    consultar_ultima_lectura_db,
)
from app.services.alertas_service import emitir_alerta
from app.services.deteccion_sensores import descripcion_sin_transmision
from app.repositories.regla_alerta_repository import reglas_vigentes
from app.services.predicciones_service import (
    actualizar_predicciones_activas,
)
from app.utils.errores import mensaje_error
from app.utils.logger import obtener_logger


logger = obtener_logger("procesos_periodicos")
ZONA_ARGENTINA = ZoneInfo("America/Argentina/Buenos_Aires")

PROCESOS_DISPONIBLES = {"predicciones", "sensores"}


def detectar_sensores_inactivos_automatico(horas=24, ahora=None, severidad="Media"):
    """
    Detecta sensores activos sin lecturas recientes, registra la alerta y
    emite los mensajes (internos y, si el contenedor tiene un único envío
    activo, los usuarios de su cliente).

    No cambia el estado del sensor ni crea incidentes.
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
        # En los textos, el contenedor se identifica por su código.
        codigo = sensor[2]
        tipo_sensor = sensor[3]
        estado = str(sensor[6]).strip().lower()

        if estado != "activo":
            continue

        resumen["sensores_activos"] += 1

        try:
            lectura = consultar_ultima_lectura_db(id_sensor)

            if lectura is None:
                resumen["sin_lecturas"].append(id_sensor)
                tipo = "Sensor sin lecturas registradas"
                descripcion = descripcion_sin_transmision(tipo_sensor, codigo)

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
                descripcion = descripcion_sin_transmision(
                    tipo_sensor, codigo, fecha, horas)

            # Una alerta por sensor, tipo y día evita duplicados
            # si el proceso se ejecuta varias veces durante el día.
            dia_deteccion = ahora.astimezone(
                ZONA_ARGENTINA
            ).date().isoformat()
            clave = f"{id_sensor}:{tipo}:{dia_deteccion}"

            from app.services.incidentes_service import (
                buscar_envios_activos_de_contenedor,
            )
            envios = buscar_envios_activos_de_contenedor(id_contenedor)

            emitir_alerta(
                sensor_id=id_sensor,
                contenedor_id=id_contenedor,
                tipo=tipo,
                severidad=severidad,
                descripcion=descripcion,
                clave_deteccion=clave,
                envio_id=envios[0] if len(envios) == 1 else None,
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
                "error": mensaje_error(error),
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


def regla_sin_transmision():
    """(horas, severidad) de la regla activa menos exigente; (24, Media) si no hay."""
    reglas = reglas_vigentes().get(("horas_sin_transmision", "MAX"))
    if not reglas:
        return 24.0, "Media"
    horas, severidad, _ = min(reglas, key=lambda r: r[0])
    return horas, severidad


def ejecutar_revision_sensores(horas=None):
    """Revisión periódica: sensores sin transmisión y lecturas recientes
    (umbrales de la carga y fallas del sensor)."""
    from app.services.incidentes_service import revisar_lecturas_sensores

    horas_regla, severidad = regla_sin_transmision()
    horas = horas or horas_regla
    logger.info(
        "Iniciando revisión de sensores. Umbral: %s horas",
        horas,
    )

    resultado = detectar_sensores_inactivos_automatico(horas=horas, severidad=severidad)
    resultado["lecturas"] = revisar_lecturas_sensores()
    return resultado


def ejecutar_todos_los_procesos(horas_sensores=None, procesos=None):
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
            resultado["errores"][proceso] = mensaje_error(error)
            logger.exception(
                "Falló el proceso periódico de %s",
                proceso,
            )

    return resultado
