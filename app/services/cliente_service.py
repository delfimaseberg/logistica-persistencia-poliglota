
from app.models.cliente import Cliente
from app.repositories.cliente_repository import (
    dato_en_uso,
    crear_cliente,
    listar_clientes,
    buscar_cliente_por_id,
    modificar_cliente,
    eliminar_cliente
)
from app.services.autenticacion import requiere_permiso
from app.utils.validaciones_datos import (
    LARGOS_CONTACTO,
    es_argentina,
    validar_email,
    validar_identificacion_fiscal,
    validar_largo,
    validar_telefono,
)
from app.utils.errores import mensaje_error


def pedir_dato(mensaje, validador, *args):  # repite la pregunta hasta que la validación pase
    while True:
        try:
            return validador(input(mensaje), *args)
        except ValueError as error:
            print(f"Error: {mensaje_error(error)}")


def _sin_repetir(campo, valor, excluir_id, texto):  # error si otro cliente ya usa ese CUIT o email
    if dato_en_uso(campo, valor, excluir_id):
        raise ValueError(f"Ya existe otro cliente con ese {texto}.")
    return valor


def pedir_datos_cliente(excluir_id=None):  # pide y valida todos los datos; la usan alta y modificación
    """Pide y valida los datos (el país antes del CUIT: de él depende el formato)."""
    razon_social = pedir_dato(
        "Razón social: ",
        lambda v: validar_largo(v, "La razón social", LARGOS_CONTACTO["razon_social"]),
    )
    pais = pedir_dato("País: ", lambda v: validar_largo(v, "El país", LARGOS_CONTACTO["pais"]))
    etiqueta = "CUIT" if es_argentina(pais) else "Identificación fiscal"  # en Argentina se pide CUIT
    cuit = pedir_dato(
        f"{etiqueta}: ",
        lambda v: _sin_repetir("cuit", validar_identificacion_fiscal(v, pais), excluir_id,  # CUIT válido y que no lo tenga otro cliente
                               "CUIT" if es_argentina(pais) else "número de identificación"),
    )
    email = pedir_dato(
        "Email: ",
        lambda v: _sin_repetir("email", validar_email(v), excluir_id, "email"),  # email válido y único
    )
    telefono = pedir_dato("Teléfono (opcional): ", validar_telefono)
    direccion = pedir_dato(
        "Dirección: ",
        lambda v: validar_largo(v, "La dirección", LARGOS_CONTACTO["direccion"]),
    )
    estado = pedir_estado_cliente()
    return razon_social, cuit, email, telefono, direccion, pais, estado


def pedir_id_cliente():  # pide el ID; la usan buscar, modificar y eliminar
    while True:
        valor = input("ID del cliente: ").strip()

        if valor.isdigit() and int(valor) > 0:
            return int(valor)

        print("Error: el ID debe ser un número entero positivo.")


def pedir_estado_cliente():  # ACTIVO o INACTIVO
    while True:
        print("\nEstado del cliente:")
        print("1. ACTIVO")
        print("2. INACTIVO")

        opcion = input("Seleccioná una opción: ").strip()

        if opcion == "1":
            return "ACTIVO"

        if opcion == "2":
            return "INACTIVO"

        print("Opción inválida. Seleccioná 1 o 2.")


def mostrar_cliente(cliente):  # imprime un cliente
    if cliente is None:
        print("Cliente no encontrado.")
        return

    print(f"""
ID: {cliente[0]}
Razón social: {cliente[1]}
CUIT: {cliente[2]}
Email: {cliente[3]}
Teléfono: {cliente[4]}
Dirección: {cliente[5]}
País: {cliente[6]}
Estado: {cliente[7]}
""")


@requiere_permiso(1)
def registrar_cliente():  # da de alta un cliente; opción 1 del menú de clientes
    print("\n--- REGISTRAR CLIENTE ---")

    razon_social, cuit, email, telefono, direccion, pais, estado = pedir_datos_cliente()

    cliente = Cliente(
        razon_social,
        cuit,
        email,
        telefono,
        direccion,
        pais,
        estado
    )

    try:
        id_cliente = crear_cliente(cliente)  # INSERT en PostgreSQL

        print("\nCliente registrado correctamente.")
        print(f"ID asignado: {id_cliente}")

    except Exception as error:
        print(f"\nError al registrar el cliente: {mensaje_error(error)}")

    input("\nPresioná Enter para continuar...")


@requiere_permiso(1)
def listar_clientes_service():  # lista los clientes; opción 2 del menú de clientes
    print("\n--- LISTADO DE CLIENTES ---")

    try:
        clientes = listar_clientes()

        if not clientes:
            print("No hay clientes registrados.")
        else:
            for cliente in clientes:
                print("-------------------------------")
                mostrar_cliente(cliente)

    except Exception as error:
        print(f"Error al listar los clientes: {mensaje_error(error)}")

    input("\nPresioná Enter para continuar...")


@requiere_permiso(1)
def buscar_cliente_service():  # muestra un cliente por ID; opción 3 del menú de clientes
    print("\n--- BUSCAR CLIENTE ---")

    id_cliente = pedir_id_cliente()

    try:
        cliente = buscar_cliente_por_id(id_cliente)
        mostrar_cliente(cliente)

    except Exception as error:
        print(f"Error al buscar el cliente: {mensaje_error(error)}")

    input("\nPresioná Enter para continuar...")


@requiere_permiso(1)
def modificar_cliente_service():  # cambia los datos de un cliente; opción 4 del menú de clientes
    print("\n--- MODIFICAR CLIENTE ---")

    id_cliente = pedir_id_cliente()

    try:
        cliente_actual = buscar_cliente_por_id(id_cliente)

        if cliente_actual is None:
            print("Cliente no encontrado.")
            input("\nPresioná Enter para continuar...")
            return

        print("\nCliente actual:")
        mostrar_cliente(cliente_actual)

        print("Ingresá los nuevos datos:")

        razon_social, cuit, email, telefono, direccion, pais, estado = (
            pedir_datos_cliente(excluir_id=id_cliente)  # al modificar no cuenta su propio CUIT o email
        )

        cliente_modificado = Cliente(
            razon_social,
            cuit,
            email,
            telefono,
            direccion,
            pais,
            estado
        )

        modificado = modificar_cliente(
            id_cliente,
            cliente_modificado
        )

        if modificado:
            print("\nCliente modificado correctamente.")
        else:
            print("\nNo se pudo modificar el cliente.")

    except Exception as error:
        print(f"\nError al modificar el cliente: {mensaje_error(error)}")

    input("\nPresioná Enter para continuar...")


@requiere_permiso(1)
def eliminar_cliente_service():  # borra un cliente; opción 5 del menú de clientes
    print("\n--- ELIMINAR CLIENTE ---")

    id_cliente = pedir_id_cliente()

    try:
        cliente = buscar_cliente_por_id(id_cliente)

        if cliente is None:
            print("Cliente no encontrado.")
            input("\nPresioná Enter para continuar...")
            return

        print("\nCliente a eliminar:")
        mostrar_cliente(cliente)

        confirmacion = input(
            "¿Seguro que querés eliminarlo? (S/N): "
        ).strip().upper()

        if confirmacion != "S":
            print("Eliminación cancelada.")
        else:
            eliminado = eliminar_cliente(id_cliente)  # si tiene usuarios, envíos o facturas, la base no deja borrarlo

            if eliminado:
                print("Cliente eliminado correctamente.")
            else:
                print("No se pudo eliminar el cliente.")

    except Exception as error:
        print(f"\nError al eliminar el cliente: {mensaje_error(error)}")

    input("\nPresioná Enter para continuar...")
