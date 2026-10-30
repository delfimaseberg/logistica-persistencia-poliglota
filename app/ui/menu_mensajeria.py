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
OPCIONES = {
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


def opciones_para(sesion):
    """Los usuarios externos no administran grupos (solo participan)."""
    interno = sesion is not None and es_interno(sesion)
    return {
        clave: opcion for clave, opcion in OPCIONES.items()
        if interno or not opcion[2]
    }


def mostrar_menu_mensajeria():
    # Disponible para cualquier usuario con sesión: cada uno ve a quién
    # puede escribir según su parte.
    if not verificar_sesion():
        return

    while True:
        sesion = obtener_sesion_actual()
        if sesion is None:
            print("\nDebe iniciar sesión para continuar.")
            return

        opciones = opciones_para(sesion)

        print("\n==========================================")
        print("               MENSAJERÍA")
        print("==========================================")
        for clave, (texto, _, _) in opciones.items():
            print(f"{clave}. {texto}")
        print("0. Volver")

        opcion = input("\nSeleccione una opción: ").strip()

        if opcion == "0":
            break

        if opcion in opciones:
            opciones[opcion][1]()
        else:
            print("\nOpción inválida.")
