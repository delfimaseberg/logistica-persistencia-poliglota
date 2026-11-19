from app.services.autenticacion import (
    es_interno,
    obtener_sesion_actual,
    verificar_sesion,
)

from app.services.mensajeria_service import (
    listar_usuarios_mensajeria_service,
    enviar_mensaje_service,
    consultar_bandeja_service,
    consultar_enviados_service,
    consultar_conversacion_service,
    marcar_leido_service,
    crear_grupo_service,
    listar_grupos_service,
    agregar_miembro_service,
    enviar_mensaje_grupo_service,
    consultar_mensajes_grupo_service
)


# (texto, función, solo internos)
OPCIONES = {  # las de True (grupos) solo las ven los internos
    "1": ("Listar usuarios con los que puedo comunicarme",
          listar_usuarios_mensajeria_service, False),
    "2": ("Enviar mensaje privado", enviar_mensaje_service, False),
    "3": ("Consultar bandeja de entrada", consultar_bandeja_service, False),
    "4": ("Consultar mensajes enviados", consultar_enviados_service, False),
    "5": ("Consultar conversación", consultar_conversacion_service, False),
    "6": ("Marcar mensaje como leído", marcar_leido_service, False),
    "7": ("Crear grupo de trabajo", crear_grupo_service, True),
    "8": ("Consultar mis grupos administrados", listar_grupos_service, True),
    "9": ("Agregar miembro a grupo", agregar_miembro_service, True),
    "10": ("Enviar mensaje a grupo", enviar_mensaje_grupo_service, False),
    "11": ("Consultar mensajes de grupo", consultar_mensajes_grupo_service, False),
}


def opciones_para(sesion):  # opciones que ve el usuario según su parte; la usa mostrar_menu_mensajeria
    """Los usuarios externos no administran grupos (solo participan).

    Las opciones visibles se numeran de forma consecutiva (1, 2, 3...).
    """
    interno = sesion is not None and es_interno(sesion)
    visibles = [opcion for opcion in OPCIONES.values() if interno or not opcion[2]]  # a los externos se les sacan las de administrar grupos
    return {str(numero): opcion for numero, opcion in enumerate(visibles, 1)}


def mostrar_menu_mensajeria():  # menú de mensajería; opción 8 del menú interno y opción de cada portal
    # Disponible para cualquier usuario con sesión: cada uno ve a quién
    # puede escribir según su parte.
    if not verificar_sesion():
        return

    while True:
        sesion = obtener_sesion_actual()
        if sesion is None:
            print("\nDebés iniciar sesión para continuar.")
            return

        opciones = opciones_para(sesion)  # se arma de nuevo en cada vuelta

        print("\n==========================================")
        print("               MENSAJERÍA")
        print("==========================================")
        for clave, (texto, _, _) in opciones.items():
            print(f"{clave}. {texto}")
        print("0. Volver")

        opcion = input("\nSeleccioná una opción: ").strip()

        if opcion == "0":
            break

        if opcion in opciones:
            opciones[opcion][1]()
        else:
            print("\nOpción inválida.")
