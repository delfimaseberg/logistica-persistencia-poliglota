
from app.services.autenticacion import verificar_permiso

from app.services.incidentes_service import (
    registrar_incidente_service,
    consultar_incidentes_service,
    cambiar_estado_incidente_service,
    detectar_alertas_service,
    consultar_alertas_service,
    atender_alerta_service
)
from app.services.reglas_alerta_service import menu_reglas_alerta


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
        print("4. Detectar anomalías y fallas de sensores (genera alertas y mensajes)")
        print("5. Consultar alertas")
        print("6. Marcar alerta como atendida")
        print("7. Reglas de alerta (umbrales)")
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

        elif opcion == "7":
            if verificar_permiso(3):
                menu_reglas_alerta()

        elif opcion == "0":
            break

        else:
            print("\nOpción inválida.")
