from app.models.usuario import Usuario
from app.repositories.usuario_repository import (
    crear_usuario,
    listar_usuarios,
    buscar_usuario_por_id,
    modificar_usuario,
    eliminar_usuario,
    existe_cliente,
    existe_rol
)
from app.repositories.cliente_repository import listar_clientes
from app.repositories.rol_repository import listar_roles
from app.repositories.usuario_repository import email_en_uso
from app.services.autenticacion import requiere_permiso
from app.services.contrasena_service import pedir_contrasena_nueva
from app.utils.validaciones_datos import LARGOS_USUARIO, validar_email, validar_largo
from app.utils.seguridad import generar_hash_contrasena
from app.utils.validaciones_terceros import describir_parte
from app.repositories.terceros_repository import (
    listar_proveedores,
    listar_operadores
)
from app.utils import formato
from app.utils.errores import mensaje_error


def pedir_dato(mensaje, validador, *args):
    while True:
        try:
            return validador(input(mensaje), *args)
        except ValueError as error:
            print(f"Error: {mensaje_error(error)}")


def validar_nombre(valor):
    return validar_largo(valor, "El nombre", LARGOS_USUARIO["nombre"])


def validar_apellido(valor):
    return validar_largo(valor, "El apellido", LARGOS_USUARIO["apellido"])


def pedir_email_libre(excluir_id=None):
    """Email válido que no use otro usuario (sin distinguir mayúsculas)."""
    while True:
        email = pedir_dato("Email: ", validar_email)
        if not email_en_uso(email, excluir_id):
            return email
        print("Error: ya existe un usuario con ese email.")


def pedir_id(mensaje):
    while True:
        valor = input(mensaje).strip()

        if valor.isdigit() and int(valor) > 0:
            return int(valor)

        print("Error: el ID debe ser un número entero positivo.")


def seleccionar_cliente():
    clientes = listar_clientes()

    if not clientes:
        print("\nNo hay clientes registrados.")
        return None

    print("\nClientes disponibles:")

    for cliente in clientes:
        print(
            f"{cliente[0]}. {cliente[1]} "
            f"(CUIT: {cliente[2]})"
        )

    while True:
        id_cliente = pedir_id(
            "\nSeleccioná el cliente: "
        )

        if existe_cliente(id_cliente):
            return id_cliente

        print("Error: seleccioná uno de los clientes disponibles.")


def _seleccionar_de(filas, titulo):
    """Lista terceros activos (id, razón social, CUIT, ...) y pide un ID."""
    activas = [fila for fila in filas if fila[8] == "ACTIVO"]

    if not activas:
        print(f"\nNo hay {titulo} activos.")
        return None

    print(f"\n{titulo.capitalize()} disponibles:")
    for fila in activas:
        print(f"{fila[0]}. {fila[1]} (CUIT: {fila[2]})")

    ids = {fila[0] for fila in activas}
    while True:
        elegido = pedir_id("\nSeleccioná el ID: ")
        if elegido in ids:
            return elegido
        print("Error: seleccioná uno de la lista.")


def seleccionar_parte():
    """Devuelve (id_cliente, id_proveedor, id_operador) o None si se cancela.

    Las tres en None = usuario interno.
    """
    while True:
        print("\nEl usuario pertenece a:")
        print("1. Un cliente")
        print("2. Un proveedor")
        print("3. Un operador logístico")
        print("4. Ninguno (usuario interno)")
        opcion = input("\nSeleccioná una opción: ").strip()

        if opcion == "1":
            id_cliente = seleccionar_cliente()
            return None if id_cliente is None else (id_cliente, None, None)
        if opcion == "2":
            id_proveedor = _seleccionar_de(listar_proveedores(), "proveedores")
            return None if id_proveedor is None else (None, id_proveedor, None)
        if opcion == "3":
            id_operador = _seleccionar_de(
                listar_operadores(), "operadores logísticos"
            )
            return None if id_operador is None else (None, None, id_operador)
        if opcion == "4":
            return (None, None, None)

        print("Error: seleccioná una opción válida.")


def seleccionar_rol():
    roles = listar_roles()

    if not roles:
        print("\nNo hay roles registrados.")
        return None

    print("\nRoles disponibles:")

    for rol in roles:
        print(
            f"{rol[0]}. {rol[1]} "
            f"(Nivel de permisos: {rol[2]})"
        )

    while True:
        id_rol = pedir_id(
            "\nSeleccioná el rol: "
        )

        if existe_rol(id_rol):
            return id_rol

        print("Error: seleccioná uno de los roles disponibles.")


def seleccionar_estado():
    while True:
        print("\nEstados disponibles:")
        print("1. ACTIVO")
        print("2. INACTIVO")

        opcion = input(
            "\nSeleccioná el estado: "
        ).strip()

        if opcion == "1":
            return "ACTIVO"

        if opcion == "2":
            return "INACTIVO"

        print("Error: seleccioná una opción válida.")

def mostrar_usuario(usuario):
    if usuario is None:
        print("Usuario no encontrado.")
        return

    # Columnas 8-10 (proveedor, operador, nombre de la parte) existen desde la
    # migración 012; se toleran filas más cortas.
    id_proveedor = usuario[8] if len(usuario) > 8 else None
    id_operador = usuario[9] if len(usuario) > 9 else None
    nombre_parte = usuario[10] if len(usuario) > 10 else None
    parte = describir_parte(usuario[1], id_proveedor, id_operador, nombre_parte)

    print(f"""
ID: {usuario[0]}
Parte: {parte}
Rol ID: {usuario[2]}
Nombre: {usuario[3]}
Apellido: {usuario[4]}
Email: {usuario[5]}
Estado: {usuario[6]}
Fecha de registro: {formato.fecha_hora(usuario[7])}{_estado_acceso(usuario)}
""")


def _estado_acceso(usuario):
    """Bloqueo e intentos fallidos (columnas 11-13, migración 016)."""
    if len(usuario) <= 11:
        return ""
    lineas = []
    if usuario[11] is not None:
        lineas.append(f"Bloqueado hasta: {formato.fecha_hora(usuario[11])} (intentos fallidos)")
    elif usuario[12]:
        lineas.append(f"Intentos fallidos seguidos: {usuario[12]}")
    if len(usuario) > 13 and usuario[13]:
        lineas.append("Debe cambiar la contraseña en el próximo inicio de sesión")
    return "".join("\n" + linea for linea in lineas)


@requiere_permiso(5)
def registrar_usuario():
    print("\n--- REGISTRAR USUARIO ---")

    parte = seleccionar_parte()

    if parte is None:
        input("\nPresioná Enter para continuar...")
        return

    id_cliente, id_proveedor, id_operador = parte

    id_rol = seleccionar_rol()

    if id_rol is None:
        input("\nPresioná Enter para continuar...")
        return

    nombre = pedir_dato("Nombre: ", validar_nombre)
    apellido = pedir_dato("Apellido: ", validar_apellido)
    email = pedir_email_libre()

    contrasena = pedir_contrasena_nueva(email, nombre, apellido, titulo="Contraseña")
    if contrasena is None:
        print("\nAlta cancelada.")
        input("\nPresioná Enter para continuar...")
        return

    contrasena_hash = generar_hash_contrasena(contrasena)
    del contrasena

    estado = seleccionar_estado()

    usuario = Usuario(
        id_cliente,
        id_rol,
        nombre,
        apellido,
        email,
        contrasena_hash,
        estado,
        id_proveedor=id_proveedor,
        id_operador=id_operador
    )

    try:
        id_usuario = crear_usuario(usuario)

        print("\nUsuario registrado correctamente.")
        print(f"ID asignado: {id_usuario}")

    except Exception as error:
        print(f"\nError al registrar el usuario: {mensaje_error(error)}")

    input("\nPresioná Enter para continuar...")


@requiere_permiso(3)
def listar_usuarios_service():
    print("\n--- LISTADO DE USUARIOS ---")

    try:
        usuarios = listar_usuarios()

        if not usuarios:
            print("No hay usuarios registrados.")

        else:
            for usuario in usuarios:
                print("-------------------------------")
                mostrar_usuario(usuario)

    except Exception as error:
        print(f"Error al listar usuarios: {mensaje_error(error)}")

    input("\nPresioná Enter para continuar...")


@requiere_permiso(3)
def buscar_usuario_service():
    print("\n--- BUSCAR USUARIO ---")

    id_usuario = pedir_id(
        "ID del usuario: "
    )

    try:
        usuario = buscar_usuario_por_id(
            id_usuario
        )

        mostrar_usuario(usuario)

    except Exception as error:
        print(
            f"Error al buscar el usuario: {mensaje_error(error)}"
        )

    input("\nPresioná Enter para continuar...")


@requiere_permiso(5)
def modificar_usuario_service():
    print("\n--- MODIFICAR USUARIO ---")

    id_usuario = pedir_id(
        "ID del usuario: "
    )

    try:
        usuario_actual = buscar_usuario_por_id(
            id_usuario
        )

        if usuario_actual is None:
            print("Usuario no encontrado.")
            input("\nPresioná Enter para continuar...")
            return

        print("\nUsuario actual:")
        mostrar_usuario(usuario_actual)

        print("\nIngresá los nuevos datos:")

        parte = seleccionar_parte()

        if parte is None:
            input("\nPresioná Enter para continuar...")
            return

        id_cliente, id_proveedor, id_operador = parte

        id_rol = seleccionar_rol()

        if id_rol is None:
            input("\nPresioná Enter para continuar...")
            return

        nombre = pedir_dato("Nombre: ", validar_nombre)
        apellido = pedir_dato("Apellido: ", validar_apellido)
        email = pedir_email_libre(excluir_id=id_usuario)

        # La contraseña no se cambia aquí: ver "Restablecer contraseña".
        estado = seleccionar_estado()

        usuario_modificado = Usuario(
            id_cliente,
            id_rol,
            nombre,
            apellido,
            email,
            None,
            estado,
            id_proveedor=id_proveedor,
            id_operador=id_operador
        )

        modificado = modificar_usuario(
            id_usuario,
            usuario_modificado
        )

        if modificado:
            print(
                "\nUsuario modificado correctamente."
            )
        else:
            print(
                "\nNo se pudo modificar el usuario."
            )

    except Exception as error:
        print(
            f"\nError al modificar el usuario: {mensaje_error(error)}"
        )

    input("\nPresioná Enter para continuar...")


@requiere_permiso(5)
def eliminar_usuario_service():
    print("\n--- ELIMINAR USUARIO ---")

    id_usuario = pedir_id(
        "ID del usuario: "
    )

    try:
        usuario = buscar_usuario_por_id(
            id_usuario
        )

        if usuario is None:
            print("Usuario no encontrado.")
            input("\nPresioná Enter para continuar...")
            return

        print("\nUsuario a eliminar:")
        mostrar_usuario(usuario)

        confirmacion = input(
            "¿Seguro que querés eliminarlo? (S/N): "
        ).strip().upper()

        if confirmacion != "S":
            print("Eliminación cancelada.")

        else:
            eliminado = eliminar_usuario(
                id_usuario
            )

            if eliminado:
                print(
                    "Usuario eliminado correctamente."
                )
            else:
                print(
                    "No se pudo eliminar el usuario."
                )

    except Exception as error:
        print(
            f"\nError al eliminar el usuario: {mensaje_error(error)}"
        )

    input("\nPresioná Enter para continuar...")