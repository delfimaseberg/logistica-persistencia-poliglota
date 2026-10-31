from app.services.autenticacion import verificar_permiso
from app.services.trazabilidad_service import (
    registrar_evento_service,
    historial_envio_service,
    seguimiento_temporal_service,
    ruta_completa_service,
    recorrido_contenedor_service,
    sincronizar_proyeccion_service,
    quien_llevo_contenedor_service,
    red_operadores_cliente_service
)


def mostrar_menu_trazabilidad():
    while True:
        if not verificar_permiso(1):
            return

        print("\n==========================================")
        print("        TRAZABILIDAD DE ENVÍOS")
        print("==========================================")
        print("1. Registrar evento logístico")
        print("2. Historial completo de un envío")
        print("3. Seguimiento temporal de un envío")
        print("4. Ruta completa de un envío")
        print("5. Recorrido de un contenedor")
        print("6. Sincronizar / reparar la red de rutas")
        print("7. ¿Quién llevó el contenedor? (operadores)")
        print("8. Red cliente - operadores - envíos")
        print("0. Volver al menú principal")

        opcion = input("\nSeleccione una opción: ").strip()

        if opcion == "1":
            registrar_evento_service()
        elif opcion == "2":
            historial_envio_service()
        elif opcion == "3":
            seguimiento_temporal_service()
        elif opcion == "4":
            ruta_completa_service()
        elif opcion == "5":
            recorrido_contenedor_service()
        elif opcion == "6":
            sincronizar_proyeccion_service()
        elif opcion == "7":
            quien_llevo_contenedor_service()
        elif opcion == "8":
            red_operadores_cliente_service()
        elif opcion == "0":
            break
        else:
            print("\nOpción inválida.")
