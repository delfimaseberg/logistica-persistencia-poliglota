
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.repositories.predicciones_repository import (
    listar_envios_analisis,
    obtener_datos_riesgo,
    guardar_prediccion,
    obtener_historial_predicciones,
    reporte_historico_incidentes,
    reporte_demoras_estimadas,
)
from app.utils.logger import obtener_logger
from app.utils import formato
from app.utils.errores import mensaje_error
from app.services.autenticacion import requiere_permiso


logger = obtener_logger("predicciones")  # registro en logs/app.log

ZONA_ARGENTINA = ZoneInfo("America/Argentina/Buenos_Aires")
ESTADOS_FINALIZADOS = {"entregado", "cancelado"}  # a estos envíos no se les calcula riesgo
ESTADOS_INCIDENTE_CERRADO = {"cerrado", "resuelto"}  # incidentes que ya no suman riesgo


def pausar():
    input("\nPresioná Enter para continuar...")


def formatear_fecha(fecha):  # fecha en hora argentina para mostrar
    if fecha is None:
        return "Sin información"

    if fecha.tzinfo is None:
        fecha = fecha.replace(tzinfo=timezone.utc)

    return fecha.astimezone(ZONA_ARGENTINA).strftime(
        "%d/%m/%Y %H:%M"
    )


def clasificar_riesgo(puntaje, datos_suficientes=True):  # nivel según el puntaje de 0 a 100; la usa calcular_riesgo
    if puntaje >= 70:  # desde 70 puntos: ALTO
        return "ALTO"

    if puntaje >= 35:  # desde 35 puntos: MEDIO
        return "MEDIO"

    if not datos_suficientes:  # sin fechas estimadas no se puede decir que es BAJO
        return "INFORMACIÓN INSUFICIENTE"

    return "BAJO"


# ------------------------------------------------------------------
# Probabilidad de demora (v4): historial de la ruta + clima + incidentes
# + plazo. Cada factor es una probabilidad p y se combinan como eventos
# independientes: 1 - (1 - p1)(1 - p2)...
# ------------------------------------------------------------------

PROB_CLIMA = {"Baja": 0.10, "Media": 0.25, "Alta": 0.45, "Extrema": 0.70}  # probabilidad de demora que aporta una alerta climática según su severidad
NIVEL_CLIMA = {"Baja": "BAJO", "Media": "MEDIO", "Alta": "ALTO", "Extrema": "EXTREMO"}  # riesgo climático que se informa según la severidad de la peor alerta
ORDEN_CLIMA = ("Baja", "Media", "Alta", "Extrema")  # severidades climáticas de menor a mayor
MIN_ENVIOS_HISTORIAL = 2  # mínimo de entregados en la ruta para usar su propia tasa de atraso
ORDEN_NIVEL = {"BAJO": 0, "INFORMACIÓN INSUFICIENTE": 0, "MEDIO": 1, "ALTO": 2}  # para comparar niveles y quedarse con el mayor


def prob_incidente(severidad):  # probabilidad de demora que aporta un incidente abierto; la usa calcular_riesgo
    valor = str(severidad).strip().lower()
    if valor in {"critica", "crítica", "critico", "crítico"}:
        return 0.40  # incidente crítico: 40 por ciento
    if valor == "alta":
        return 0.30  # alta: 30 por ciento
    if valor == "media":
        return 0.20  # media: 20 por ciento
    return 0.10  # baja u otra: 10 por ciento


def combinar_probabilidades(probabilidades):  # combina los factores como independientes: 1 menos el producto de (1 - p); la usa calcular_riesgo
    restante = 1.0
    for p in probabilidades:
        restante *= 1.0 - min(max(float(p), 0.0), 1.0)
    return 1.0 - restante


def nivel_por_probabilidad(probabilidad):  # nivel según la probabilidad de demora; la usa calcular_riesgo
    if probabilidad >= 0.60:  # desde 60 por ciento: ALTO
        return "ALTO"
    if probabilidad >= 0.30:  # desde 30 por ciento: MEDIO
        return "MEDIO"
    return "BAJO"


def _utc(fecha):  # le pone UTC a las fechas sin zona horaria
    if fecha is None:
        return None
    return fecha.replace(tzinfo=timezone.utc) if fecha.tzinfo is None else fecha


def _se_superponen(inicio_a, fin_a, inicio_b, fin_b):  # si dos períodos se pisan
    return inicio_a < fin_b and inicio_b < fin_a


def alertas_que_afectan(datos, alertas, ahora):  # alertas climáticas que caen en el lugar y el momento del viaje; la usa calcular_riesgo
    """Alertas climáticas que afectan al envío.

    - Por ciudad: la de un tramo (origen o destino) durante ese tramo, de la
      salida a la llegada estimada (el último tramo, hasta hoy si está demorado).
    - Por país (de origen o destino) o ciudad del envío: durante todo el viaje.
    """
    from app.repositories.alerta_climatica_repository import normalizar_lugar

    tramos = [t for t in (datos.get("tramos") or []) if len(t) >= 4]
    salidas = [_utc(t[0]) for t in tramos if t[0] is not None]
    llegadas = [_utc(t[1]) for t in tramos if t[1] is not None]
    inicio_viaje = min(salidas) if salidas else (_utc(datos.get("fecha_creacion")) or ahora)
    fin_viaje = max(llegadas + [ahora]) if llegadas else ahora
    ultima_llegada = max(llegadas) if llegadas else None

    ventanas = []      # (lugares normalizados, inicio, fin)
    lugares_envio = {normalizar_lugar(x) for x in (  # países y ciudades del envío: cuentan durante todo el viaje
        datos.get("pais_origen"), datos.get("pais_destino"),
        datos.get("origen"), datos.get("destino")) if x}
    ventanas.append((lugares_envio, inicio_viaje, fin_viaje))
    for salida, llegada, origen, destino, *_ in tramos:  # ciudades de cada tramo: cuentan solo mientras dura ese tramo
        if salida is None or llegada is None:
            continue
        fin = _utc(llegada)
        if fin == ultima_llegada:  # si el último tramo está demorado, se estira hasta hoy
            fin = max(fin, ahora)
        ventanas.append(({normalizar_lugar(origen), normalizar_lugar(destino)},
                         _utc(salida), fin))

    afectan = []
    for alerta in alertas:
        inicio, fin = _utc(alerta.get("inicio")), _utc(alerta.get("fin"))
        lugar = alerta.get("ubicacion_normalizada")
        if inicio is None or fin is None:
            continue
        if any(lugar in lugares and _se_superponen(a, b, inicio, fin)  # afecta si coincide el lugar y se superponen los períodos
               for lugares, a, b in ventanas):
            afectan.append(alerta)
    return afectan


def mas_severa_por_ubicacion(alertas):  # deja una sola alerta por lugar, la más severa; la usa calcular_riesgo
    """Una sola alerta por ubicación: la más severa (no se combinan).

    Evita contar dos veces el mismo fenómeno registrado por duplicado.
    A igual severidad, queda la que empieza antes.
    """
    elegidas = {}
    for alerta in sorted(alertas, key=lambda a: _utc(a.get("inicio")) or datetime.min.replace(tzinfo=timezone.utc)):
        lugar = alerta.get("ubicacion_normalizada")
        actual = elegidas.get(lugar)
        if actual is None or (ORDEN_CLIMA.index(alerta["severidad"])
                              > ORDEN_CLIMA.index(actual["severidad"])):
            elegidas[lugar] = alerta
    return list(elegidas.values())


def texto_probabilidad(prediccion):  # probabilidad de demora en texto; la usan las pantallas de predicciones y el reporte predictivo
    """Dato principal de una predicción: la probabilidad de demora.

    Sin fechas estimadas no se puede estimar (o es un mínimo, si ya da ALTO).
    """
    probabilidad = prediccion.get("probabilidad_demora")
    if probabilidad is None:
        return "sin dato (evaluación anterior)"
    if prediccion.get("nivel_riesgo") == "INFORMACIÓN INSUFICIENTE":
        return "no se puede estimar (faltan fechas estimadas de llegada)"
    texto = formato.porcentaje(probabilidad)
    if not prediccion.get("datos_suficientes", True):
        return f"al menos {texto} (faltan fechas estimadas de llegada)"
    return texto


def historial_de_ruta(datos, historial):  # tasa de atraso de la ruta del envío; la usa armar_datos_riesgo
    """{ruta, envios, atrasados, tasa, fuente} para la ruta del envío.

    Con menos de MIN_ENVIOS_HISTORIAL envíos propios se usa la tasa general.
    """
    from app.repositories.alerta_climatica_repository import normalizar_lugar

    clave = (normalizar_lugar(datos.get("origen")), normalizar_lugar(datos.get("destino")))
    ruta = historial["rutas"].get(clave)
    nombre = f"{datos.get('origen')} -> {datos.get('destino')}"
    if ruta and ruta["envios"] >= MIN_ENVIOS_HISTORIAL:  # con suficientes envíos se usa la tasa de la ruta
        return {"ruta": nombre, "envios": ruta["envios"], "atrasados": ruta["atrasados"],
                "tasa": ruta["atrasados"] / ruta["envios"], "fuente": "ruta"}
    general = historial["general"]
    tasa = general["atrasados"] / general["envios"] if general["envios"] else 0.0  # si no, la tasa general de todas las rutas
    return {"ruta": nombre, "envios": ruta["envios"] if ruta else 0,
            "atrasados": ruta["atrasados"] if ruta else 0, "tasa": tasa,
            "fuente": "general"}


def calcular_historial_rutas(entregados, retrasos):  # cuenta entregados y atrasados por ruta; la usa historial_rutas
    """Rutas que suelen atrasarse.

    entregados: [(id_envio, origen, destino, llegada_estimada, fecha_entrega)].
    retrasos: {id_envio: (cantidad de eventos RETRASO, motivo)}.
    Un envío está atrasado si se entregó después de la llegada estimada o si
    se informó al menos un RETRASO.
    """
    from app.repositories.alerta_climatica_repository import normalizar_lugar

    rutas = {}
    general = {"envios": 0, "atrasados": 0}
    for id_envio, origen, destino, estimada, entrega in entregados:
        tarde = (estimada is not None and entrega is not None  # atrasado: entregado después de la llegada estimada...
                 and _utc(entrega) > _utc(estimada))
        atrasado = tarde or retrasos.get(id_envio, (0, None))[0] > 0  # ...o con algún evento RETRASO
        clave = (normalizar_lugar(origen), normalizar_lugar(destino))  # la ruta es el par origen y destino
        ruta = rutas.setdefault(clave, {"ruta": f"{origen} -> {destino}",
                                        "envios": 0, "atrasados": 0})
        ruta["envios"] += 1
        ruta["atrasados"] += int(atrasado)
        general["envios"] += 1
        general["atrasados"] += int(atrasado)
    return {"rutas": rutas, "general": general}


def historial_rutas():  # historial de atrasos por ruta; la usan las predicciones y el reporte predictivo
    """Historial desde PostgreSQL (entregas) y MongoDB (eventos RETRASO)."""
    from app.repositories.predicciones_repository import envios_entregados_por_ruta
    from app.services.reportes_service import retrasos_por_envio

    entregados = envios_entregados_por_ruta()  # entregas de PostgreSQL
    return calcular_historial_rutas(entregados, retrasos_por_envio([f[0] for f in entregados]))  # más los eventos RETRASO de MongoDB


def armar_datos_riesgo(id_envio, historial=None):  # junta todo lo que necesita calcular_riesgo; la usan evaluar un envío y actualizar predicciones
    """Datos del envío + alertas climáticas de sus lugares + historial de su ruta."""
    from app.repositories.alerta_climatica_repository import (
        alertas_para_lugares,
        normalizar_lugar,
    )

    datos = obtener_datos_riesgo(id_envio)  # envío, tramos e incidentes de PostgreSQL
    if datos is None:
        return None
    lugares = {normalizar_lugar(x) for x in (
        datos.get("pais_origen"), datos.get("pais_destino"),
        datos.get("origen"), datos.get("destino")) if x}
    for tramo in datos.get("tramos") or []:
        if len(tramo) >= 4:
            lugares |= {normalizar_lugar(tramo[2]), normalizar_lugar(tramo[3])}
    datos["alertas_climaticas"] = alertas_para_lugares(lugares)  # alertas climáticas de esos lugares en MongoDB
    datos["historial_ruta"] = historial_de_ruta(datos, historial or historial_rutas())
    return datos


def calcular_riesgo(datos, ahora=None):  # calcula puntaje, probabilidad de demora y nivel de riesgo; la usan evaluar un envío y actualizar predicciones
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

            if fechas:  # con fechas estimadas se puede evaluar el plazo
                datos_suficientes = True

                fechas = [
                    fecha.replace(tzinfo=timezone.utc)
                    if fecha.tzinfo is None else fecha
                    for fecha in fechas
                ]

                llegada_estimada = max(fechas)  # la llegada del último tramo

                horas_vencidas = (
                    ahora - llegada_estimada
                ).total_seconds() / 3600

                if horas_vencidas > 48:  # más de 48 horas tarde: 60 puntos
                    puntaje_demora = 60
                    motivos.append(
                        "Llegada estimada superada por más de 48 horas"
                    )

                elif horas_vencidas > 24:  # más de 24 horas tarde: 45 puntos
                    puntaje_demora = 45
                    motivos.append(
                        "Llegada estimada superada por más de 24 horas"
                    )

                elif horas_vencidas > 0:  # vencida: 30 puntos
                    puntaje_demora = 30
                    motivos.append(
                        "Llegada estimada superada"
                    )

                elif horas_vencidas > -24:  # falta menos de un día: 15 puntos
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

    incidentes_abiertos = [  # solo los incidentes que siguen abiertos
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
                puntaje_operativo += 35  # incidente crítico: 35 puntos

            elif valor == "alta":
                puntaje_operativo += 25  # alta: 25

            elif valor == "media":
                puntaje_operativo += 15  # media: 15

            else:
                puntaje_operativo += 10  # baja: 10

        puntaje_operativo = min(puntaje_operativo, 60)  # los incidentes suman como máximo 60 puntos

        if incidentes_abiertos:
            motivos.append(
                f"{len(incidentes_abiertos)} incidente(s) abierto(s)"
            )

        if prioridad == "alta":
            puntaje_operativo += 10  # prioridad alta suma 10 puntos
            motivos.append("Envío de prioridad alta")

    puntaje = min(  # puntaje total: plazo más incidentes, hasta 100
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

    # --- v4: clima, historial de la ruta y probabilidad de demora ---
    evalua_clima = "alertas_climaticas" in datos
    historial = datos.get("historial_ruta")
    afectan = []
    factores = []

    if not finalizado:
        if historial and historial["tasa"] > 0:  # factor 1: la tasa de atraso de la ruta
            factores.append(("Historial de la ruta", historial["tasa"]))
            texto_fuente = (
                f"{historial['atrasados']} de {historial['envios']} envíos de la ruta atrasados"
                if historial["fuente"] == "ruta"
                else "sin historial suficiente de la ruta: se usa la tasa general"
            )
            motivos.append(
                f"Ruta {historial['ruta']}: {formato.porcentaje(historial['tasa'] * 100, 0)} de atraso histórico "
                f"({texto_fuente})"
            )

        if evalua_clima:  # factor 2: la alerta climática más severa que afecta al viaje
            afectan = mas_severa_por_ubicacion(
                alertas_que_afectan(datos, datos["alertas_climaticas"], ahora))
            if afectan:
                peor = max(afectan, key=lambda a: ORDEN_CLIMA.index(a["severidad"]))
                factores.append(("Clima", PROB_CLIMA[peor["severidad"]]))  # cuenta solo la peor, no todas
                for alerta in afectan:
                    motivos.append(
                        f"Alerta climática {alerta['severidad']}: {alerta['fenomeno']} "
                        f"en {alerta['ubicacion']}"
                    )

        for severidad, _ in incidentes_abiertos:  # factor 3: cada incidente abierto
            factores.append((f"Incidente {severidad}", prob_incidente(severidad)))

        if puntaje_demora >= 30:  # factor 4: llegada estimada vencida; la demora ya es segura
            factores.append(("Llegada estimada vencida", 1.0))

    if finalizado:
        riesgo_climatico = "NO APLICA"
    elif not evalua_clima:
        riesgo_climatico = "NO EVALUADO"
    elif not afectan:
        riesgo_climatico = "SIN ALERTAS"
    else:
        riesgo_climatico = NIVEL_CLIMA[
            max(afectan, key=lambda a: ORDEN_CLIMA.index(a["severidad"]))["severidad"]]

    if not motivos:
        motivos.append(
            "No se detectaron factores de riesgo con las reglas actuales"
        )

    probabilidad = combinar_probabilidades(p for _, p in factores)  # combina los cuatro factores

    nivel_riesgo = clasificar_riesgo(
        puntaje,
        datos_suficientes=datos_suficientes
    )

    # El nivel general es el mayor entre el del puntaje y el de la
    # probabilidad. Sin fechas estimadas la probabilidad es parcial: solo
    # reemplaza "información insuficiente" si ya da riesgo ALTO.
    nivel_probabilidad = nivel_por_probabilidad(probabilidad)  # nivel final: el mayor entre puntaje y probabilidad
    if ORDEN_NIVEL[nivel_probabilidad] > ORDEN_NIVEL[nivel_riesgo] and (
            nivel_riesgo != "INFORMACIÓN INSUFICIENTE" or nivel_probabilidad == "ALTO"):
        nivel_riesgo = nivel_probabilidad

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
        # Entidad Predicción de Riesgo de la consigna: envío, riesgo
        # climático, riesgo operativo, probabilidad de demora y fecha.
        "riesgo_climatico": riesgo_climatico,
        "riesgo_operativo": nivel_operativo,
        "probabilidad_demora": round(probabilidad * 100, 1),
        "alertas_climaticas": [
            {"ubicacion": a["ubicacion"], "fenomeno": a["fenomeno"],
             "severidad": a["severidad"], "desde": a.get("fecha_desde"),
             "hasta": a.get("fecha_hasta")}
            for a in afectan
        ],
        "historial_ruta": historial,
        "factores_probabilidad": [
            {"factor": nombre, "probabilidad": round(p, 4)} for nombre, p in factores
        ],
        "incidentes_abiertos": len(incidentes_abiertos),
        "motivos": motivos,
        "metodo": "reglas_heuristicas_v4",
        "fecha_calculo": ahora
    }


def mostrar_prediccion(prediccion):  # imprime una predicción; la usan evaluar un envío y el historial de predicciones
    print("\n------------------------------------------")
    print(f"Envío: {prediccion['envio_id']}")
    print(f"Cliente: {prediccion['cliente']}")
    print(f"Estado: {prediccion['estado_envio']}")
    print(f"Probabilidad de demora: {texto_probabilidad(prediccion)}")
    print(f"Nivel de riesgo: {prediccion['nivel_riesgo']}")

    nivel_operativo = (prediccion.get("riesgo_operativo")
                       or prediccion.get("nivel_riesgo_operativo"))

    if nivel_operativo:
        print(f"Riesgo operativo: {nivel_operativo}")

    print(f"Riesgo climático: {prediccion['riesgo_climatico']}")
    historial = prediccion.get("historial_ruta")
    if historial:
        print(f"Historial de la ruta {historial['ruta']}: "
              f"{historial['atrasados']} atrasado(s) de {historial['envios']} entregado(s)"
              + (" (se usa la tasa general por falta de historial)"
                 if historial.get("fuente") == "general" else ""))

    if not prediccion.get("datos_suficientes", True):
        print(
            "Evaluación parcial: faltan datos de llegada estimada."
        )
        print(
            "El riesgo operativo sigue siendo válido, "
            "pero no representa el riesgo total."
        )

    print(
        f"Fecha: {formatear_fecha(prediccion['fecha_calculo'])}"
    )

    print("Factores considerados:")

    for motivo in prediccion["motivos"]:
        print(f" - {motivo}")


def seleccionar_envio():  # elige un envío de la lista; la usan las opciones 1 y 2
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


@requiere_permiso(1)
def evaluar_envio_service():  # calcula el riesgo de un envío; opción 1 del menú de predicciones
    print("\n--- EVALUAR RIESGO DE ENVÍO ---")

    try:
        id_envio = seleccionar_envio()

        if id_envio is None:
            return

        datos = armar_datos_riesgo(id_envio)
        prediccion = calcular_riesgo(datos)

        mostrar_prediccion(prediccion)

        guardar = input(
            "\n¿Guardar la evaluación? (S/N): "
        ).strip().upper()

        if guardar == "S":
            id_prediccion = guardar_prediccion(prediccion)  # se guarda en MongoDB solo si se confirma

            logger.info(
                "Evaluación guardada para envío %s: %s",
                id_envio,
                prediccion["nivel_riesgo"]
            )

            print(
                "Evaluación guardada."
            )

    except Exception as error:
        logger.exception(
            "Error al evaluar un envío"
        )
        print(f"\nError al evaluar el envío: {mensaje_error(error)}")

    finally:
        pausar()


@requiere_permiso(1)
def historial_predicciones_service():  # predicciones guardadas de un envío; opción 2 del menú de predicciones
    print("\n--- HISTORIAL DE PREDICCIONES ---")

    try:
        id_envio = seleccionar_envio()

        if id_envio is None:
            return

        historial = obtener_historial_predicciones(id_envio)  # las últimas 10 de MongoDB

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
        print(f"\nError al consultar historial: {mensaje_error(error)}")

    finally:
        pausar()


@requiere_permiso(1)
def historico_incidentes_service():  # incidentes por cliente y promedio por envío; opción 4 del menú de predicciones
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
                f"{formato.numero(promedio, 2)}"
            )

    except Exception as error:
        logger.exception(
            "Error al generar análisis de incidentes"
        )
        print(f"\nError al generar análisis: {mensaje_error(error)}")

    finally:
        pausar()


@requiere_permiso(1)
def demoras_estimadas_service():  # envíos activos con la llegada estimada ya pasada; opción 5 del menú de predicciones
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
        print(f"\nError al consultar demoras: {mensaje_error(error)}")

    finally:
        pausar()


def actualizar_predicciones_activas():  # calcula y guarda la predicción de cada envío activo; la usan la opción 6 y el proceso periódico
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

    # El historial de rutas se calcula una sola vez para todo el lote.
    historial = historial_rutas() if activos else None  # se calcula una vez y sirve para todos

    for envio in activos:
        id_envio = envio[0]

        try:
            datos = armar_datos_riesgo(id_envio, historial)
            prediccion = calcular_riesgo(datos)

            guardar_prediccion(prediccion)  # en MongoDB, una por envío y por día

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
                "probabilidad": texto_probabilidad(prediccion),
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
                "error": mensaje_error(error)
            })

            logger.exception(
                "Error al actualizar predicción del envío %s",
                id_envio
            )

    return resumen


@requiere_permiso(3)
def actualizar_predicciones_service():  # confirma y muestra el resultado de actualizar todas; opción 6 del menú de predicciones
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
            "¿Guardar las evaluaciones? (S/N): "
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
                    f"{resultado['nivel_riesgo']} | "
                    f"probabilidad de demora: {resultado['probabilidad']}"
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
            f"\nError al actualizar predicciones: {mensaje_error(error)}"
        )

    finally:
        pausar()
