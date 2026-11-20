
from app.services.autenticacion import verificar_permiso

from app.services.predicciones_service import (
    evaluar_envio_service,
    historial_predicciones_service,
    historico_incidentes_service,
    demoras_estimadas_service,
    actualizar_predicciones_service
)
from app.services.clima_service import menu_alertas_climaticas
from app.services import reportes_pantallas as pantallas


def mostrar_menu_predicciones():  # menú de análisis y predicciones; opción 11 del menú principal
    if not verificar_permiso(1):
        return

    while True:
        if not verificar_permiso(1):  # se controla en cada vuelta por si venció la sesión
            return

        print("\n==========================================")
        print("         ANÁLISIS Y PREDICCIONES")
        print("==========================================")
        print("1. Evaluar riesgo de un envío")
        print("2. Consultar historial de predicciones")
        print("3. Ranking de clientes por volumen transportado")
        print("4. Análisis histórico de incidentes")
        print("5. Envíos con llegada estimada vencida")
        print("6. Actualizar predicciones de envíos activos")
        print("7. Alertas climáticas (registrar, listar, anular)")
        print("0. Volver al menú principal")

        opcion = input("\nSeleccioná una opción: ").strip()

        if opcion == "1":  # calcula el riesgo de un envío y deja guardarlo en MongoDB
            evaluar_envio_service()
        elif opcion == "2":
            historial_predicciones_service()
        elif opcion == "3":
            # El mismo reporte que Reportes -> Rankings y desempeño.
            pantallas.REPORTES_RANKINGS["2"][1]()
        elif opcion == "4":
            historico_incidentes_service()
        elif opcion == "5":
            demoras_estimadas_service()
        elif opcion == "6":
            if verificar_permiso(3):  # actualizar todas las predicciones pide nivel 3
                actualizar_predicciones_service()
        elif opcion == "7":
            if verificar_permiso(3):  # las alertas climáticas también
                menu_alertas_climaticas()
        elif opcion == "0":
            break
        else:
            print("\nOpción inválida.")
