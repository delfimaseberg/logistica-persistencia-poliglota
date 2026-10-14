
from datetime import datetime
from zoneinfo import ZoneInfo

from app.services.autenticacion import obtener_sesion_actual

from app.repositories.mensajeria_repository import (
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


ZONA_ARGENTINA = ZoneInfo("America/Argentina/Buenos_Aires")


def pausar():
    input("\nPresioná Enter para continuar...")


def pedir_id(mensaje):
    while True:
        valor = input(mensaje).strip()

        if valor.isdigit() and int(valor) > 0:
            return int(valor)

        print("Ingresá un número entero positivo.")


def obtener_id_usuario_actual():
    sesion = obtener_sesion_actual()

    if sesion is None:
        raise PermissionError("Debés iniciar sesión.")

    return sesion["id_usuario"]


def pedir_contenido():
    contenido = input("Mensaje: ").strip()

    if not contenido:
        raise ValueError("El mensaje no puede estar vacío.")

    if len(contenido) > 2000:
        raise ValueError("El mensaje no puede superar 2000 caracteres.")

    return contenido


def formatear_fecha(fecha):
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


def obtener_nombre_usuario(id_usuario):
    if id_usuario is None:
        return "Sin usuario"

    try:
        usuario = obtener_usuario_activo(id_usuario)

        if usuario:
            return f"{usuario[1]} {usuario[2]}"

    except Exception:
        pass

    return f"Usuario {id_usuario}"


def seleccionar_de_lista(elementos, titulo, obtener_descripcion):
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


def seleccionar_usuario(excluir_id=None):
    usuarios = obtener_usuarios_activos()

    if excluir_id is not None:
        usuarios = [
            usuario
            for usuario in usuarios
            if usuario[0] != excluir_id
        ]

    return seleccionar_de_lista(
        usuarios,
        "SELECCIONAR USUARIO",
        lambda usuario: (
            f"{usuario[1]} {usuario[2]} "
            f"({usuario[3]})"
        )
    )


def seleccionar_grupo(id_usuario):
    grupos = listar_grupos_usuario(id_usuario)

    return seleccionar_de_lista(
        grupos,
        "SELECCIONAR GRUPO",
        lambda grupo: (
            f"{grupo['nombre']} "
            f"({len(grupo.get('miembros', []))} miembros)"
        )
    )


def mostrar_mensaje(mensaje, numero=None):
    print("-" * 45)

    if numero is not None:
        print(f"Mensaje {numero}")

    print(
        f"De: {obtener_nombre_usuario(mensaje.get('remitente_id'))}"
    )

    if mensaje.get("tipo") == "Privado":
        print(
            f"Para: {obtener_nombre_usuario(mensaje.get('destinatario_id'))}"
        )

    print(f"Fecha: {formatear_fecha(mensaje.get('fecha_hora'))}")
    print(f"Contenido: {mensaje.get('contenido', '')}")

    if mensaje.get("tipo") == "Privado":
        estado = "Leído" if mensaje.get("leido") else "No leído"
        print(f"Estado: {estado}")


def listar_usuarios_mensajeria_service():
    print("\n--- USUARIOS DISPONIBLES ---")

    try:
        usuarios = obtener_usuarios_activos()

        if not usuarios:
            print("No hay usuarios activos.")
            return

        for numero, usuario in enumerate(usuarios, start=1):
            print(
                f"{numero}. {usuario[1]} {usuario[2]} "
                f"| Email: {usuario[3]}"
            )

    except Exception as error:
        print(f"Error al consultar usuarios: {error}")

    finally:
        pausar()


def enviar_mensaje_service():
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

        registrar_mensaje_privado(
            remitente_id,
            destinatario_id,
            contenido
        )

        print("\nMensaje enviado correctamente.")

    except Exception as error:
        print(f"Error al enviar mensaje: {error}")

    finally:
        pausar()


def consultar_bandeja_service():
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
        print(f"Error al consultar bandeja: {error}")

    finally:
        pausar()


def consultar_enviados_service():
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
        print(f"Error al consultar mensajes: {error}")

    finally:
        pausar()


def consultar_conversacion_service():
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
        print(f"Error al consultar conversación: {error}")

    finally:
        pausar()


def marcar_leido_service():
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
                f"{obtener_nombre_usuario(item.get('remitente_id'))}"
                f" | {item.get('contenido', '')[:60]}"
                f" | {formatear_fecha(item.get('fecha_hora'))}"
            )
        )

        if mensaje is None:
            print("Operación cancelada.")
            return

        if marcar_mensaje_leido(
            str(mensaje["_id"]),
            id_usuario
        ):
            print("\nMensaje marcado como leído.")
        else:
            print("No se pudo actualizar el mensaje.")

    except Exception as error:
        print(f"Error al actualizar mensaje: {error}")

    finally:
        pausar()


def crear_grupo_service():
    print("\n--- CREAR GRUPO DE TRABAJO ---")

    try:
        creador_id = obtener_id_usuario_actual()

        nombre = input("Nombre del grupo: ").strip()
        descripcion = input("Descripción: ").strip()

        if not nombre or len(nombre) > 100:
            print("El nombre debe tener entre 1 y 100 caracteres.")
            return

        if len(descripcion) > 500:
            print("La descripción no puede superar 500 caracteres.")
            return

        crear_grupo(
            nombre,
            descripcion,
            creador_id
        )

        print("\nGrupo creado correctamente.")
        print("Quedaste registrado como administrador del grupo.")

    except Exception as error:
        print(f"Error al crear grupo: {error}")

    finally:
        pausar()


def listar_grupos_service():
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
        print(f"Error al consultar grupos: {error}")

    finally:
        pausar()



def agregar_miembro_service():
    print("\n--- AGREGAR MIEMBRO A GRUPO ---")

    try:
        id_usuario = obtener_id_usuario_actual()

        grupos = [
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

        usuarios = obtener_usuarios_activos()

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
            lambda usuario: (
                f"{usuario[1]} {usuario[2]} "
                f"({usuario[3]})"
            )
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
        print(f"Error al agregar miembro: {error}")

    finally:
        pausar()



def enviar_mensaje_grupo_service():
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

        registrar_mensaje_grupo(
            id_usuario,
            str(grupo["_id"]),
            contenido
        )

        print("\nMensaje enviado al grupo correctamente.")

    except Exception as error:
        print(f"Error al enviar mensaje al grupo: {error}")

    finally:
        pausar()


def consultar_mensajes_grupo_service():
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
        print(f"Error al consultar mensajes del grupo: {error}")

    finally:
        pausar()
