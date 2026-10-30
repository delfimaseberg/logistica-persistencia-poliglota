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
from app.utils.validaciones import (
    texto_obligatorio,
    validar_email
)
from app.utils.seguridad import generar_hash_contrasena
from app.utils.validaciones_terceros import describir_parte
from app.repositories.terceros_repository import (
    listar_proveedores,
    listar_operadores
)


def pedir_dato(mensaje, validador, *args):
    while True:
        try:
            return validador(input(mensaje), *args)
        except ValueError as error:
            print(f"Error: {error}")


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
            "\nSeleccione el cliente: "
        )

        if existe_cliente(id_cliente):
            return id_cliente

        print("Error: seleccione uno de los clientes disponibles.")


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
        elegido = pedir_id("\nSeleccione el ID: ")
        if elegido in ids:
            return elegido
        print("Error: seleccione uno de la lista.")


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
        opcion = input("\nSeleccione una opción: ").strip()

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

        print("Error: seleccione una opción válida.")


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
            "\nSeleccione el rol: "
        )

        if existe_rol(id_rol):
            return id_rol

        print("Error: seleccione uno de los roles disponibles.")


def seleccionar_estado():
    while True:
        print("\nEstados disponibles:")
        print("1. ACTIVO")
        print("2. INACTIVO")

        opcion = input(
            "\nSeleccione el estado: "
        ).strip()

        if opcion == "1":
            return "ACTIVO"

        if opcion == "2":
            return "INACTIVO"

        print("Error: seleccione una opción válida.")

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
Fecha de registro: {usuario[7]}
""")


def registrar_usuario():
    print("\n--- REGISTRAR USUARIO ---")

    parte = seleccionar_parte()

    if parte is None:
        input("\nPresione Enter para continuar...")
        return

    id_cliente, id_proveedor, id_operador = parte

    id_rol = seleccionar_rol()

    if id_rol is None:
        input("\nPresione Enter para continuar...")
        return

    nombre = pedir_dato(
        "Nombre: ",
        texto_obligatorio,
        "El nombre"
    )

    apellido = pedir_dato(
        "Apellido: ",
        texto_obligatorio,
        "El apellido"
    )

    email = pedir_dato(
        "Email: ",
        validar_email
    )

    contrasena = pedir_dato(
        "Contraseña: ",
        texto_obligatorio,
        "La contraseña"
    )

    contrasena_hash = generar_hash_contrasena(
        contrasena
    )

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
        print(f"\nError al registrar el usuario: {error}")

    input("\nPresione Enter para continuar...")


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
        print(f"Error al listar usuarios: {error}")

    input("\nPresione Enter para continuar...")


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
            f"Error al buscar el usuario: {error}"
        )

    input("\nPresione Enter para continuar...")


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
            input("\nPresione Enter para continuar...")
            return

        print("\nUsuario actual:")
        mostrar_usuario(usuario_actual)

        print("\nIngrese los nuevos datos:")

        parte = seleccionar_parte()

        if parte is None:
            input("\nPresione Enter para continuar...")
            return

        id_cliente, id_proveedor, id_operador = parte

        id_rol = seleccionar_rol()

        if id_rol is None:
            input("\nPresione Enter para continuar...")
            return

        nombre = pedir_dato(
            "Nombre: ",
            texto_obligatorio,
            "El nombre"
        )

        apellido = pedir_dato(
            "Apellido: ",
            texto_obligatorio,
            "El apellido"
        )

        email = pedir_dato(
            "Email: ",
            validar_email
        )

        contrasena = pedir_dato(
            "Nueva contraseña: ",
            texto_obligatorio,
            "La contraseña"
        )

        contrasena_hash = generar_hash_contrasena(
            contrasena
        )

        estado = seleccionar_estado()

        usuario_modificado = Usuario(
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
            f"\nError al modificar el usuario: {error}"
        )

    input("\nPresione Enter para continuar...")


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
            input("\nPresione Enter para continuar...")
            return

        print("\nUsuario a eliminar:")
        mostrar_usuario(usuario)

        confirmacion = input(
            "¿Está seguro de que desea eliminarlo? (S/N): "
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
            f"\nError al eliminar el usuario: {error}"
        )

    input("\nPresione Enter para continuar...")