
from app.services.autenticacion import verificar_permiso

from app.services.predicciones_service import (
    evaluar_envio_service,
    historial_predicciones_service,
    ranking_clientes_service,
    historico_incidentes_service,
    demoras_estimadas_service,
    actualizar_predicciones_service
)


def mostrar_menu_predicciones():
    if not verificar_permiso(1):
        return

    while True:
        if not verificar_permiso(1):
            return

        print("\n==========================================")
        print("         ANÁLISIS Y PREDICCIONES")
        print("==========================================")
        print("1. Evaluar riesgo de un envío")
        print("2. Consultar historial de predicciones")
        print("3. Ranking de clientes por envíos")
        print("4. Análisis histórico de incidentes")
        print("5. Envíos con llegada estimada vencida")
        print("6. Actualizar predicciones de envíos activos")
        print("0. Volver al menú principal")

        opcion = input("\nSeleccione una opción: ").strip()

        if opcion == "1":
            evaluar_envio_service()
        elif opcion == "2":
            historial_predicciones_service()
        elif opcion == "3":
            ranking_clientes_service()
        elif opcion == "4":
            historico_incidentes_service()
        elif opcion == "5":
            demoras_estimadas_service()
        elif opcion == "6":
            if verificar_permiso(3):
                actualizar_predicciones_service()
        elif opcion == "0":
            break
        else:
            print("\nOpción inválida.")
