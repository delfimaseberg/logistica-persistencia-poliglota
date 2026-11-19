
from datetime import datetime
from zoneinfo import ZoneInfo

from app.services.autenticacion import (
    es_interno,
    obtener_sesion_actual,
    parte_de,
)

from app.repositories.mensajeria_repository import (
    obtener_destinatarios_permitidos,
    obtener_usuario_activo,
    obtener_usuarios_activos,
    registrar_mensaje_privado,
    obtener_bandeja_entrada,
    obtener_mensajes_enviados,
    obtener_conversacion,
    marcar_mensaje_leido,
    contar_mensajes_no_leidos,
    crear_grupo,
    buscar_grupo,
    listar_grupos_usuario,
    usuario_es_miembro,
    agregar_miembro_grupo,
    registrar_mensaje_grupo,
    obtener_mensajes_grupo
)
from app.utils.errores import mensaje_error


ZONA_ARGENTINA = ZoneInfo("America/Argentina/Buenos_Aires")  # para mostrar las fechas


def pausar():
    input("\nPresioná Enter para continuar...")


def pedir_id(mensaje):  # pide un número entero positivo
    while True:
        valor = input(mensaje).strip()

        if valor.isdigit() and int(valor) > 0:
            return int(valor)

        print("Ingresá un número entero positivo.")


def obtener_id_usuario_actual():  # id del usuario de la sesión; la usan todas las opciones
    sesion = obtener_sesion_actual()

    if sesion is None:
        raise PermissionError("Debés iniciar sesión.")

    return sesion["id_usuario"]


def destinatarios_para_sesion():  # a quién puede escribir el usuario según su parte; la usan listar, elegir y validar destinatario
    """Usuarios a los que puede escribir el usuario de la sesión (por parte)."""
    sesion = obtener_sesion_actual()

    if sesion is None:
        raise PermissionError("Debés iniciar sesión.")

    tipo, id_parte = parte_de(sesion)  # la parte sale siempre de la sesión
    return obtener_destinatarios_permitidos(
        sesion["id_usuario"], tipo, id_parte
    )


def validar_destinatario(destinatario_id):  # segundo control al enviar; la usa enviar_mensaje_service
    """El servicio también controla al enviar, no solo la lista."""
    permitidos = {usuario[0] for usuario in destinatarios_para_sesion()}

    if destinatario_id not in permitidos:
        raise PermissionError(
            "No podés enviar mensajes a ese usuario."
        )


def puede_ver_emails():  # solo los internos ven los emails de los demás
    sesion = obtener_sesion_actual()
    return sesion is not None and es_interno(sesion)


def exigir_interno_para_grupos():  # solo internos crean grupos y agregan miembros
    sesion = obtener_sesion_actual()

    if sesion is None or not es_interno(sesion):
        raise PermissionError(
            "Solo los usuarios internos crean grupos y agregan miembros."
        )


def pedir_contenido():  # pide el texto del mensaje, hasta 2000 caracteres
    contenido = input("Mensaje: ").strip()

    if not contenido:
        raise ValueError("El mensaje no puede estar vacío.")

    if len(contenido) > 2000:
        raise ValueError("El mensaje no puede superar 2000 caracteres.")

    return contenido


def formatear_fecha(fecha):  # fecha en hora argentina
    if fecha is None:
        return "Sin fecha"

    if isinstance(fecha, str):
        try:
            fecha = datetime.fromisoformat(fecha)
        except ValueError:
            return fecha

    if fecha.tzinfo is None:
        fecha = fecha.replace(tzinfo=ZoneInfo("UTC"))

    return fecha.astimezone(ZONA_ARGENTINA).strftime(
        "%d/%m/%Y %H:%M"
    )


def obtener_nombre_usuario(id_usuario):  # nombre del usuario para mostrar
    if id_usuario is None:
        return "Sin usuario"

    try:
        usuario = obtener_usuario_activo(id_usuario)

        if usuario:
            return f"{usuario[1]} {usuario[2]}"

    except Exception:
        pass

    return f"Usuario {id_usuario}"


def seleccionar_de_lista(elementos, titulo, obtener_descripcion):  # lista numerada para elegir; la usan las pantallas de mensajería
    if not elementos:
        print("\nNo hay elementos disponibles.")
        return None

    print(f"\n--- {titulo} ---")

    for numero, elemento in enumerate(elementos, start=1):
        print(f"{numero}. {obtener_descripcion(elemento)}")

    print("0. Cancelar")

    while True:
        opcion = input("\nSeleccioná una opción: ").strip()

        if opcion == "0":
            return None

        if opcion.isdigit():
            indice = int(opcion) - 1

            if 0 <= indice < len(elementos):
                return elementos[indice]

        print("Opción inválida. Intentá nuevamente.")


def seleccionar_usuario(excluir_id=None):  # elige un destinatario permitido; la usan enviar y conversación
    # Solo los destinatarios permitidos para la parte del usuario.
    usuarios = destinatarios_para_sesion()
    con_email = puede_ver_emails()

    if excluir_id is not None:
        usuarios = [
            usuario
            for usuario in usuarios
            if usuario[0] != excluir_id
        ]

    return seleccionar_de_lista(
        usuarios,
        "SELECCIONAR USUARIO",
        lambda usuario: describir_usuario(usuario, con_email)
    )


def describir_usuario(usuario, mostrar_email=True):  # nombre, email (si corresponde) y parte
    """'Nombre Apellido (email) - Parte'. La parte es opcional en la fila.

    A los usuarios externos no se les muestra el email de los demás.
    """
    texto = f"{usuario[1]} {usuario[2]}"
    if mostrar_email:
        texto += f" ({usuario[3]})"
    if len(usuario) > 4 and usuario[4]:
        texto += f" - {usuario[4]}"
    return texto


def seleccionar_grupo(id_usuario):  # elige uno de los grupos del usuario
    grupos = listar_grupos_usuario(id_usuario)

    return seleccionar_de_lista(
        grupos,
        "SELECCIONAR GRUPO",
        lambda grupo: (
            f"{grupo['nombre']} "
            f"({len(grupo.get('miembros', []))} miembros)"
        )
    )


def nombre_remitente(mensaje):  # nombre de quien mandó el mensaje
    """Los mensajes de alertas los emite el sistema, no un usuario."""
    if mensaje.get("remitente_nombre"):
        return mensaje["remitente_nombre"]
    return obtener_nombre_usuario(mensaje.get("remitente_id"))


def mostrar_mensaje(mensaje, numero=None):  # imprime un mensaje; la usan bandeja, enviados, conversación y grupos
    print("-" * 45)

    if numero is not None:
        print(f"Mensaje {numero}")

    if mensaje.get("tipo") == "Alerta":
        print("*** ALERTA ***")

    print(f"De: {nombre_remitente(mensaje)}")

    if mensaje.get("tipo") == "Privado":
        print(
            f"Para: {obtener_nombre_usuario(mensaje.get('destinatario_id'))}"
        )

    print(f"Fecha: {formatear_fecha(mensaje.get('fecha_hora'))}")
    print(f"Contenido: {mensaje.get('contenido', '')}")

    if mensaje.get("tipo") in ("Privado", "Alerta"):
        estado = "Leído" if mensaje.get("leido") else "No leído"
        print(f"Estado: {estado}")


def listar_usuarios_mensajeria_service():  # a quién le puedo escribir; opción 1 de mensajería
    print("\n--- USUARIOS DISPONIBLES ---")

    try:
        usuarios = destinatarios_para_sesion()
        con_email = puede_ver_emails()

        if not usuarios:
            print("No hay usuarios con los que puedas comunicarte.")
            return

        for numero, usuario in enumerate(usuarios, start=1):
            print(f"{numero}. {describir_usuario(usuario, con_email)}")

    except Exception as error:
        print(f"Error al consultar usuarios: {mensaje_error(error)}")

    finally:
        pausar()


def enviar_mensaje_service():  # manda un mensaje privado; opción 2 de mensajería
    print("\n--- ENVIAR MENSAJE PRIVADO ---")

    try:
        remitente_id = obtener_id_usuario_actual()

        destinatario = seleccionar_usuario(
            excluir_id=remitente_id
        )

        if destinatario is None:
            print("Operación cancelada.")
            return

        destinatario_id = destinatario[0]
        validar_destinatario(destinatario_id)  # se vuelve a controlar antes de guardar

        print(
            f"\nDestinatario: {destinatario[1]} {destinatario[2]}"
        )

        contenido = pedir_contenido()

        confirmar = input(
            "¿Enviar mensaje? (S/N): "
        ).strip().upper()

        if confirmar != "S":
            print("Envío cancelado.")
            return

        registrar_mensaje_privado(  # se guarda en MongoDB como no leído
            remitente_id,
            destinatario_id,
            contenido
        )

        print("\nMensaje enviado correctamente.")

    except Exception as error:
        print(f"Error al enviar mensaje: {mensaje_error(error)}")

    finally:
        pausar()


def consultar_bandeja_service():  # mensajes privados y de alertas recibidos; opción 3 de mensajería
    print("\n--- BANDEJA DE ENTRADA ---")

    try:
        id_usuario = obtener_id_usuario_actual()

        mensajes = obtener_bandeja_entrada(id_usuario)
        pendientes = contar_mensajes_no_leidos(id_usuario)

        print(f"\nMensajes no leídos: {pendientes}")
        print(f"Mensajes mostrados: {len(mensajes)}")

        if not mensajes:
            print("No tenés mensajes recibidos.")
            return

        for numero, mensaje in enumerate(mensajes, start=1):
            mostrar_mensaje(mensaje, numero)

    except Exception as error:
        print(f"Error al consultar bandeja: {mensaje_error(error)}")

    finally:
        pausar()


def consultar_enviados_service():  # mensajes privados enviados; opción 4 de mensajería
    print("\n--- MENSAJES ENVIADOS ---")

    try:
        id_usuario = obtener_id_usuario_actual()
        mensajes = obtener_mensajes_enviados(id_usuario)

        if not mensajes:
            print("No tenés mensajes enviados.")
            return

        print(f"\nMensajes encontrados: {len(mensajes)}")

        for numero, mensaje in enumerate(mensajes, start=1):
            mostrar_mensaje(mensaje, numero)

    except Exception as error:
        print(f"Error al consultar mensajes: {mensaje_error(error)}")

    finally:
        pausar()


def consultar_conversacion_service():  # mensajes con otro usuario, en orden; opción 5 de mensajería
    print("\n--- CONSULTAR CONVERSACIÓN ---")

    try:
        id_usuario = obtener_id_usuario_actual()

        otro_usuario = seleccionar_usuario(
            excluir_id=id_usuario
        )

        if otro_usuario is None:
            print("Operación cancelada.")
            return

        mensajes = obtener_conversacion(
            id_usuario,
            otro_usuario[0]
        )

        print(
            f"\nConversación con "
            f"{otro_usuario[1]} {otro_usuario[2]}"
        )

        if not mensajes:
            print("Todavía no hay mensajes en esta conversación.")
            return

        for numero, mensaje in enumerate(mensajes, start=1):
            mostrar_mensaje(mensaje, numero)

    except Exception as error:
        print(f"Error al consultar conversación: {mensaje_error(error)}")

    finally:
        pausar()


def marcar_leido_service():  # marca como leído un mensaje recibido; opción 6 de mensajería
    print("\n--- MARCAR MENSAJE COMO LEÍDO ---")

    try:
        id_usuario = obtener_id_usuario_actual()

        mensajes = [
            mensaje
            for mensaje in obtener_bandeja_entrada(id_usuario)
            if not mensaje.get("leido", False)
        ]

        if not mensajes:
            print("No tenés mensajes pendientes de lectura.")
            return

        mensaje = seleccionar_de_lista(
            mensajes,
            "MENSAJES NO LEÍDOS",
            lambda item: (
                f"{nombre_remitente(item)}"
                f" | {item.get('contenido', '')[:60]}"
                f" | {formatear_fecha(item.get('fecha_hora'))}"
            )
        )

        if mensaje is None:
            print("Operación cancelada.")
            return

        if marcar_mensaje_leido(  # solo si el mensaje es para este usuario
            str(mensaje["_id"]),
            id_usuario
        ):
            print("\nMensaje marcado como leído.")
        else:
            print("No se pudo actualizar el mensaje.")

    except Exception as error:
        print(f"Error al actualizar mensaje: {mensaje_error(error)}")

    finally:
        pausar()


def crear_grupo_service():  # crea un grupo de trabajo; opción 7 de mensajería (internos)
    print("\n--- CREAR GRUPO DE TRABAJO ---")

    try:
        exigir_interno_para_grupos()  # control en el servicio, además del menú
        creador_id = obtener_id_usuario_actual()

        nombre = input("Nombre del grupo: ").strip()
        descripcion = input("Descripción: ").strip()

        if not nombre or len(nombre) > 100:
            print("El nombre debe tener entre 1 y 100 caracteres.")
            return

        if len(descripcion) > 500:
            print("La descripción no puede superar 500 caracteres.")
            return

        crear_grupo(  # el creador queda como administrador
            nombre,
            descripcion,
            creador_id
        )

        print("\nGrupo creado correctamente.")
        print("Quedaste registrado como administrador del grupo.")

    except Exception as error:
        print(f"Error al crear grupo: {mensaje_error(error)}")

    finally:
        pausar()


def listar_grupos_service():  # grupos en los que participa el usuario; opción 8 de mensajería (internos)
    print("\n--- MIS GRUPOS DE TRABAJO ---")

    try:
        id_usuario = obtener_id_usuario_actual()
        grupos = listar_grupos_usuario(id_usuario)

        if not grupos:
            print("Todavía no pertenecés a ningún grupo.")
            return

        print(f"\nGrupos encontrados: {len(grupos)}")

        for numero, grupo in enumerate(grupos, start=1):
            print("-" * 45)
            print(f"{numero}. {grupo['nombre']}")
            print(
                f"Descripción: {grupo.get('descripcion', '')}"
            )
            print(
                f"Miembros: {len(grupo.get('miembros', []))}"
            )
            print(
                f"Creado: {formatear_fecha(grupo.get('fecha_creacion'))}"
            )

    except Exception as error:
        print(f"Error al consultar grupos: {mensaje_error(error)}")

    finally:
        pausar()



def agregar_miembro_service():  # suma un usuario a un grupo propio; opción 9 de mensajería (internos)
    print("\n--- AGREGAR MIEMBRO A GRUPO ---")

    try:
        exigir_interno_para_grupos()
        id_usuario = obtener_id_usuario_actual()

        grupos = [  # solo los grupos que creó este usuario
            grupo
            for grupo in listar_grupos_usuario(id_usuario)
            if grupo.get("creador_id") == id_usuario
        ]

        grupo = seleccionar_de_lista(
            grupos,
            "MIS GRUPOS ADMINISTRADOS",
            lambda item: item["nombre"]
        )

        if grupo is None:
            print("Operación cancelada.")
            return

        usuarios = obtener_usuarios_activos()  # a un grupo se puede sumar a cualquier usuario activo

        usuarios_disponibles = [
            usuario
            for usuario in usuarios
            if not usuario_es_miembro(grupo, usuario[0])
        ]

        if not usuarios_disponibles:
            print("\nTodos los usuarios activos ya pertenecen al grupo.")
            return

        nuevo_usuario = seleccionar_de_lista(
            usuarios_disponibles,
            "USUARIOS DISPONIBLES PARA AGREGAR",
            describir_usuario
        )

        if nuevo_usuario is None:
            print("Operación cancelada.")
            return

        if agregar_miembro_grupo(
            str(grupo["_id"]),
            nuevo_usuario[0]
        ):
            print(
                f"\nSe agregó a "
                f"{nuevo_usuario[1]} {nuevo_usuario[2]} "
                f"al grupo {grupo['nombre']}."
            )
        else:
            print("No se pudo agregar el usuario. Puede que ya pertenezca al grupo.")

    except Exception as error:
        print(f"Error al agregar miembro: {mensaje_error(error)}")

    finally:
        pausar()



def enviar_mensaje_grupo_service():  # manda un mensaje a un grupo; opción 10 de mensajería
    print("\n--- ENVIAR MENSAJE A GRUPO ---")

    try:
        id_usuario = obtener_id_usuario_actual()

        grupo = seleccionar_grupo(id_usuario)

        if grupo is None:
            print("Operación cancelada.")
            return

        print(f"\nGrupo seleccionado: {grupo['nombre']}")

        contenido = pedir_contenido()

        confirmar = input(
            "¿Enviar mensaje? (S/N): "
        ).strip().upper()

        if confirmar != "S":
            print("Envío cancelado.")
            return

        registrar_mensaje_grupo(  # controla que sea miembro y lo guarda en MongoDB
            id_usuario,
            str(grupo["_id"]),
            contenido
        )

        print("\nMensaje enviado al grupo correctamente.")

    except Exception as error:
        print(f"Error al enviar mensaje al grupo: {mensaje_error(error)}")

    finally:
        pausar()


def consultar_mensajes_grupo_service():  # mensajes de un grupo; opción 11 de mensajería
    print("\n--- CONSULTAR MENSAJES DE GRUPO ---")

    try:
        id_usuario = obtener_id_usuario_actual()

        grupo = seleccionar_grupo(id_usuario)

        if grupo is None:
            print("Operación cancelada.")
            return

        mensajes = obtener_mensajes_grupo(
            str(grupo["_id"]),
            id_usuario
        )

        print(f"\nGrupo: {grupo['nombre']}")
        print(f"Mensajes encontrados: {len(mensajes)}")

        if not mensajes:
            print("Este grupo todavía no tiene mensajes.")
            return

        for numero, mensaje in enumerate(mensajes, start=1):
            mostrar_mensaje(mensaje, numero)

    except Exception as error:
        print(f"Error al consultar mensajes del grupo: {mensaje_error(error)}")

    finally:
        pausar()
