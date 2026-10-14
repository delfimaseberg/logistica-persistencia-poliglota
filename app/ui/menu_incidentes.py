
from app.services.autenticacion import verificar_permiso

from app.services.incidentes_service import (
    registrar_incidente_service,
    consultar_incidentes_service,
    cambiar_estado_incidente_service,
    detectar_alertas_service,
    consultar_alertas_service,
    atender_alerta_service
)


def mostrar_menu_incidentes():
    if not verificar_permiso(1):
        return

    while True:
        if not verificar_permiso(1):
            return

        print("\n==========================================")
        print("       GESTIÓN DE INCIDENTES Y ALERTAS")
        print("==========================================")
        print("1. Registrar incidente")
        print("2. Consultar incidentes")
        print("3. Actualizar estado de incidente")
        print("4. Detectar anomalías IoT y generar alertas")
        print("5. Consultar alertas")
        print("6. Marcar alerta como atendida")
        print("0. Volver al menú principal")

        opcion = input("\nSeleccione una opción: ").strip()

        if opcion == "1":
            registrar_incidente_service()

        elif opcion == "2":
            consultar_incidentes_service()

        elif opcion == "3":
            cambiar_estado_incidente_service()

        elif opcion == "4":
            detectar_alertas_service()

        elif opcion == "5":
            consultar_alertas_service()

        elif opcion == "6":
            atender_alerta_service()

        elif opcion == "0":
            break

        else:
            print("\nOpción inválida.")
