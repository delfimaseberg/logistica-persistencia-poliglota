
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.repositories.predicciones_repository import (
    listar_envios_analisis,
    obtener_datos_riesgo,
    guardar_prediccion,
    obtener_historial_predicciones,
    reporte_clientes_por_envios,
    reporte_historico_incidentes,
    reporte_demoras_estimadas,
)
from app.utils.logger import obtener_logger


logger = obtener_logger("predicciones")

ZONA_ARGENTINA = ZoneInfo("America/Argentina/Buenos_Aires")
ESTADOS_FINALIZADOS = {"entregado", "cancelado"}
ESTADOS_INCIDENTE_CERRADO = {"cerrado", "resuelto"}


def pausar():
    input("\nPresioná Enter para continuar...")


def formatear_fecha(fecha):
    if fecha is None:
        return "Sin información"

    if fecha.tzinfo is None:
        fecha = fecha.replace(tzinfo=timezone.utc)

    return fecha.astimezone(ZONA_ARGENTINA).strftime(
        "%d/%m/%Y %H:%M"
    )


def clasificar_riesgo(puntaje, datos_suficientes=True):
    if puntaje >= 70:
        return "ALTO"

    if puntaje >= 35:
        return "MEDIO"

    if not datos_suficientes:
        return "INFORMACIÓN INSUFICIENTE"

    return "BAJO"


def calcular_riesgo(datos, ahora=None):
    if datos is None:
        raise ValueError("El envío no existe.")

    ahora = ahora or datetime.now(timezone.utc)

    if ahora.tzinfo is None:
        raise ValueError(
            "La fecha de cálculo debe tener zona horaria."
        )

    estado = str(datos["estado"]).strip().lower()
    prioridad = str(datos["prioridad"]).strip().lower()
    finalizado = estado in ESTADOS_FINALIZADOS

    puntaje_demora = 0
    puntaje_operativo = 0
    motivos = []
    datos_suficientes = False

    tramos = datos.get("tramos") or []
    incidentes = datos.get("incidentes") or []

    if not finalizado:
        if tramos:
            fechas = [
                tramo[1]
                for tramo in tramos
                if tramo[1] is not None
            ]

            if fechas:
                datos_suficientes = True

                fechas = [
                    fecha.replace(tzinfo=timezone.utc)
                    if fecha.tzinfo is None else fecha
                    for fecha in fechas
                ]

                llegada_estimada = max(fechas)

                horas_vencidas = (
                    ahora - llegada_estimada
                ).total_seconds() / 3600

                if horas_vencidas > 48:
                    puntaje_demora = 60
                    motivos.append(
                        "Llegada estimada superada por más de 48 horas"
                    )

                elif horas_vencidas > 24:
                    puntaje_demora = 45
                    motivos.append(
                        "Llegada estimada superada por más de 24 horas"
                    )

                elif horas_vencidas > 0:
                    puntaje_demora = 30
                    motivos.append(
                        "Llegada estimada superada"
                    )

                elif horas_vencidas > -24:
                    puntaje_demora = 15
                    motivos.append(
                        "Faltan menos de 24 horas para la llegada estimada"
                    )

            else:
                motivos.append(
                    "Los tramos no tienen fecha estimada de llegada"
                )

        else:
            motivos.append(
                "Sin tramos registrados: no se puede evaluar la demora"
            )

    incidentes_abiertos = [
        incidente
        for incidente in incidentes
        if str(incidente[1]).strip().lower()
        not in ESTADOS_INCIDENTE_CERRADO
    ]

    if not finalizado:
        for severidad, _ in incidentes_abiertos:
            valor = str(severidad).strip().lower()

            if valor in {
                "critica", "crítica", "critico", "crítico"
            }:
                puntaje_operativo += 35

            elif valor == "alta":
                puntaje_operativo += 25

            elif valor == "media":
                puntaje_operativo += 15

            else:
                puntaje_operativo += 10

        puntaje_operativo = min(puntaje_operativo, 60)

        if incidentes_abiertos:
            motivos.append(
                f"{len(incidentes_abiertos)} incidente(s) abierto(s)"
            )

        if prioridad == "alta":
            puntaje_operativo += 10
            motivos.append("Envío de prioridad alta")

    puntaje = min(
        100,
        puntaje_demora + puntaje_operativo
    )

    if finalizado:
        motivos = [
            "Envío finalizado: no requiere evaluación de riesgo activo"
        ]

        puntaje = 0
        puntaje_demora = 0
        puntaje_operativo = 0
        datos_suficientes = True

    if not motivos:
        motivos.append(
            "No se detectaron factores de riesgo con las reglas actuales"
        )

    nivel_riesgo = clasificar_riesgo(
        puntaje,
        datos_suficientes=datos_suficientes
    )

    nivel_operativo = clasificar_riesgo(
        puntaje_operativo
    )

    return {
        "envio_id": int(datos["envio_id"]),
        "cliente": datos["cliente"],
        "estado_envio": datos["estado"],
        "puntaje_riesgo": puntaje,
        "nivel_riesgo": nivel_riesgo,
        "datos_suficientes": datos_suficientes,
        "evaluacion_parcial": (
            not datos_suficientes and not finalizado
        ),
        "puntaje_demora": puntaje_demora,
        "puntaje_operativo": puntaje_operativo,
        "nivel_riesgo_operativo": nivel_operativo,
        "riesgo_climatico": "NO EVALUADO",
        "incidentes_abiertos": len(incidentes_abiertos),
        "motivos": motivos,
        "metodo": "reglas_heuristicas_v3",
        "fecha_calculo": ahora
    }


def mostrar_prediccion(prediccion):
    print("\n------------------------------------------")
    print(f"Envío: {prediccion['envio_id']}")
    print(f"Cliente: {prediccion['cliente']}")
    print(f"Estado: {prediccion['estado_envio']}")
    print(f"Nivel de riesgo: {prediccion['nivel_riesgo']}")
    print(f"Puntaje: {prediccion['puntaje_riesgo']}/100")
    print(f"Riesgo por demora: {prediccion['puntaje_demora']}")
    print(f"Riesgo operativo: {prediccion['puntaje_operativo']}")

    nivel_operativo = prediccion.get(
        "nivel_riesgo_operativo"
    )

    if nivel_operativo:
        print(f"Nivel de riesgo operativo: {nivel_operativo}")

    print(f"Riesgo climático: {prediccion['riesgo_climatico']}")

    if not prediccion.get("datos_suficientes", True):
        print(
            "Evaluación parcial: faltan datos de llegada estimada."
        )
        print(
            "El puntaje operativo sigue siendo válido, "
            "pero no representa el riesgo total."
        )

    print(
        f"Fecha: {formatear_fecha(prediccion['fecha_calculo'])}"
    )

    print("Factores considerados:")

    for motivo in prediccion["motivos"]:
        print(f" - {motivo}")


def seleccionar_envio():
    envios = listar_envios_analisis()

    if not envios:
        print("\nNo hay envíos registrados.")
        return None

    print("\n--- SELECCIONAR ENVÍO ---")

    for numero, envio in enumerate(envios, 1):
        print(
            f"{numero}. Envío {envio[0]} | {envio[1]} | "
            f"{envio[2]} -> {envio[3]} | {envio[4]}"
        )

    print("0. Cancelar")

    while True:
        opcion = input(
            "\nSeleccioná una opción: "
        ).strip()

        if opcion == "0":
            return None

        if opcion.isdigit() and 1 <= int(opcion) <= len(envios):
            return envios[int(opcion) - 1][0]

        print("Opción inválida.")


def evaluar_envio_service():
    print("\n--- EVALUAR RIESGO DE ENVÍO ---")

    try:
        id_envio = seleccionar_envio()

        if id_envio is None:
            return

        datos = obtener_datos_riesgo(id_envio)
        prediccion = calcular_riesgo(datos)

        mostrar_prediccion(prediccion)

        guardar = input(
            "\n¿Guardar evaluación en MongoDB? (S/N): "
        ).strip().upper()

        if guardar == "S":
            id_prediccion = guardar_prediccion(prediccion)

            logger.info(
                "Evaluación guardada para envío %s: %s",
                id_envio,
                prediccion["nivel_riesgo"]
            )

            print(
                f"Evaluación guardada. ID: {id_prediccion}"
            )

    except Exception as error:
        logger.exception(
            "Error al evaluar un envío"
        )
        print(f"\nError al evaluar el envío: {error}")

    finally:
        pausar()


def historial_predicciones_service():
    print("\n--- HISTORIAL DE PREDICCIONES ---")

    try:
        id_envio = seleccionar_envio()

        if id_envio is None:
            return

        historial = obtener_historial_predicciones(id_envio)

        if not historial:
            print(
                "\nEste envío todavía no tiene evaluaciones guardadas."
            )
            return

        print(f"\nÚltimas {len(historial)} evaluaciones:")

        for prediccion in historial:
            mostrar_prediccion(prediccion)

    except Exception as error:
        logger.exception(
            "Error al consultar historial de predicciones"
        )
        print(f"\nError al consultar historial: {error}")

    finally:
        pausar()


def ranking_clientes_service():
    print("\n--- RANKING DE CLIENTES POR ENVÍOS ---")

    try:
        registros = reporte_clientes_por_envios()

        if not registros:
            print("No hay datos disponibles.")
            return

        for posicion, (cliente, cantidad) in enumerate(
            registros, 1
        ):
            print(
                f"{posicion}. {cliente}: {cantidad} envío(s)"
            )

    except Exception as error:
        logger.exception(
            "Error al generar ranking de clientes"
        )
        print(f"\nError al generar ranking: {error}")

    finally:
        pausar()


def historico_incidentes_service():
    print("\n--- ANÁLISIS HISTÓRICO DE INCIDENTES ---")

    try:
        registros = reporte_historico_incidentes()

        if not registros:
            print("No hay datos disponibles.")
            return

        for cliente, envios, incidentes, abiertos in registros:
            promedio = incidentes / envios if envios else 0

            print("\n------------------------------------------")
            print(f"Cliente: {cliente}")
            print(f"Envíos: {envios}")
            print(f"Incidentes registrados: {incidentes}")
            print(f"Incidentes abiertos: {abiertos}")
            print(
                "Promedio de incidentes por envío: "
                f"{promedio:.2f}"
            )

    except Exception as error:
        logger.exception(
            "Error al generar análisis de incidentes"
        )
        print(f"\nError al generar análisis: {error}")

    finally:
        pausar()


def demoras_estimadas_service():
    print("\n--- ENVÍOS CON LLEGADA ESTIMADA VENCIDA ---")

    try:
        registros = reporte_demoras_estimadas()

        if not registros:
            print(
                "No hay envíos con fecha estimada vencida."
            )
            return

        for id_envio, cliente, estado, fecha in registros:
            print("\n------------------------------------------")
            print(f"Envío: {id_envio}")
            print(f"Cliente: {cliente}")
            print(f"Estado: {estado}")
            print(
                f"Llegada estimada: {formatear_fecha(fecha)}"
            )

        print(
            "\nNota: una fecha estimada vencida no confirma "
            "por sí sola la demora real de entrega."
        )

    except Exception as error:
        logger.exception(
            "Error al consultar llegadas estimadas vencidas"
        )
        print(f"\nError al consultar demoras: {error}")

    finally:
        pausar()


def actualizar_predicciones_activas():
    """
    Calcula y guarda las evaluaciones de todos los envíos activos.

    No solicita datos por consola ni imprime resultados.
    Puede ser llamada desde el menú o desde un proceso programado.
    """
    envios = listar_envios_analisis()

    activos = [
        envio
        for envio in envios
        if str(envio[4]).strip().lower()
        not in ESTADOS_FINALIZADOS
    ]

    resumen = {
        "total": len(activos),
        "guardadas": 0,
        "errores": 0,
        "riesgos_altos": 0,
        "informacion_insuficiente": 0,
        "resultados": []
    }

    for envio in activos:
        id_envio = envio[0]

        try:
            datos = obtener_datos_riesgo(id_envio)
            prediccion = calcular_riesgo(datos)

            guardar_prediccion(prediccion)

            resumen["guardadas"] += 1

            if prediccion["nivel_riesgo"] == "ALTO":
                resumen["riesgos_altos"] += 1

            if (
                prediccion["nivel_riesgo"]
                == "INFORMACIÓN INSUFICIENTE"
            ):
                resumen["informacion_insuficiente"] += 1

            resumen["resultados"].append({
                "envio_id": id_envio,
                "nivel_riesgo": prediccion["nivel_riesgo"],
                "puntaje": prediccion["puntaje_riesgo"],
                "guardada": True
            })

            logger.info(
                "Predicción actualizada. Envío=%s, riesgo=%s",
                id_envio,
                prediccion["nivel_riesgo"]
            )

        except Exception as error:
            resumen["errores"] += 1

            resumen["resultados"].append({
                "envio_id": id_envio,
                "guardada": False,
                "error": str(error)
            })

            logger.exception(
                "Error al actualizar predicción del envío %s",
                id_envio
            )

    return resumen


def actualizar_predicciones_service():
    print("\n--- ACTUALIZAR PREDICCIONES DE RIESGO ---")

    try:
        envios = listar_envios_analisis()

        activos = [
            envio
            for envio in envios
            if str(envio[4]).strip().lower()
            not in ESTADOS_FINALIZADOS
        ]

        if not activos:
            print("No hay envíos activos para evaluar.")
            return

        print(f"Se evaluarán {len(activos)} envío(s).")

        confirmar = input(
            "¿Guardar las evaluaciones en MongoDB? (S/N): "
        ).strip().upper()

        if confirmar != "S":
            print("Operación cancelada.")
            return

        resumen = actualizar_predicciones_activas()

        for resultado in resumen["resultados"]:
            id_envio = resultado["envio_id"]

            if resultado["guardada"]:
                print(
                    f"Envío {id_envio}: "
                    f"{resultado['nivel_riesgo']} "
                    f"({resultado['puntaje']}/100)"
                )
            else:
                print(
                    f"Error en envío {id_envio}: "
                    f"{resultado['error']}"
                )

        print("\nResultado:")
        print(
            f"Evaluaciones guardadas: {resumen['guardadas']}"
        )
        print(
            f"Riesgos altos: {resumen['riesgos_altos']}"
        )
        print(
            "Información insuficiente: "
            f"{resumen['informacion_insuficiente']}"
        )
        print(f"Errores: {resumen['errores']}")

    except Exception as error:
        logger.exception(
            "Error general al actualizar predicciones"
        )
        print(
            f"\nError al actualizar predicciones: {error}"
        )

    finally:
        pausar()
