
from app.models.cliente import Cliente
from app.repositories.cliente_repository import (
    crear_cliente,
    listar_clientes,
    buscar_cliente_por_id,
    modificar_cliente,
    eliminar_cliente
)
from app.utils.validaciones import (
    texto_obligatorio,
    validar_email,
    validar_telefono
)


def pedir_dato(mensaje, validador, *args):
    while True:
        try:
            return validador(input(mensaje), *args)
        except ValueError as error:
            print(f"Error: {error}")


def pedir_id_cliente():
    while True:
        valor = input("ID del cliente: ").strip()

        if valor.isdigit() and int(valor) > 0:
            return int(valor)

        print("Error: el ID debe ser un número entero positivo.")


def pedir_estado_cliente():
    while True:
        print("\nEstado del cliente:")
        print("1. ACTIVO")
        print("2. INACTIVO")

        opcion = input("Seleccione una opción: ").strip()

        if opcion == "1":
            return "ACTIVO"

        if opcion == "2":
            return "INACTIVO"

        print("Opción inválida. Seleccione 1 o 2.")


def mostrar_cliente(cliente):
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


def registrar_cliente():
    print("\n--- REGISTRAR CLIENTE ---")

    razon_social = pedir_dato(
        "Razón social: ",
        texto_obligatorio,
        "La razón social"
    )

    cuit = pedir_dato(
        "CUIT: ",
        texto_obligatorio,
        "El CUIT"
    )

    email = pedir_dato(
        "Email: ",
        validar_email
    )

    telefono = pedir_dato(
        "Teléfono: ",
        validar_telefono
    )

    direccion = pedir_dato(
        "Dirección: ",
        texto_obligatorio,
        "La dirección"
    )

    pais = pedir_dato(
        "País: ",
        texto_obligatorio,
        "El país"
    )

    estado = pedir_estado_cliente()

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
        id_cliente = crear_cliente(cliente)

        print("\nCliente registrado correctamente.")
        print(f"ID asignado: {id_cliente}")

    except Exception as error:
        print(f"\nError al registrar el cliente: {error}")

    input("\nPresione Enter para continuar...")


def listar_clientes_service():
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
        print(f"Error al listar los clientes: {error}")

    input("\nPresione Enter para continuar...")


def buscar_cliente_service():
    print("\n--- BUSCAR CLIENTE ---")

    id_cliente = pedir_id_cliente()

    try:
        cliente = buscar_cliente_por_id(id_cliente)
        mostrar_cliente(cliente)

    except Exception as error:
        print(f"Error al buscar el cliente: {error}")

    input("\nPresione Enter para continuar...")


def modificar_cliente_service():
    print("\n--- MODIFICAR CLIENTE ---")

    id_cliente = pedir_id_cliente()

    try:
        cliente_actual = buscar_cliente_por_id(id_cliente)

        if cliente_actual is None:
            print("Cliente no encontrado.")
            input("\nPresione Enter para continuar...")
            return

        print("\nCliente actual:")
        mostrar_cliente(cliente_actual)

        print("Ingrese los nuevos datos:")

        razon_social = pedir_dato(
            "Razón social: ",
            texto_obligatorio,
            "La razón social"
        )

        cuit = pedir_dato(
            "CUIT: ",
            texto_obligatorio,
            "El CUIT"
        )

        email = pedir_dato(
            "Email: ",
            validar_email
        )

        telefono = pedir_dato(
            "Teléfono: ",
            validar_telefono
        )

        direccion = pedir_dato(
            "Dirección: ",
            texto_obligatorio,
            "La dirección"
        )

        pais = pedir_dato(
            "País: ",
            texto_obligatorio,
            "El país"
        )

        estado = pedir_estado_cliente()

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
        print(f"\nError al modificar el cliente: {error}")

    input("\nPresione Enter para continuar...")


def eliminar_cliente_service():
    print("\n--- ELIMINAR CLIENTE ---")

    id_cliente = pedir_id_cliente()

    try:
        cliente = buscar_cliente_por_id(id_cliente)

        if cliente is None:
            print("Cliente no encontrado.")
            input("\nPresione Enter para continuar...")
            return

        print("\nCliente a eliminar:")
        mostrar_cliente(cliente)

        confirmacion = input(
            "¿Está seguro de que desea eliminarlo? (S/N): "
        ).strip().upper()

        if confirmacion != "S":
            print("Eliminación cancelada.")
        else:
            eliminado = eliminar_cliente(id_cliente)

            if eliminado:
                print("Cliente eliminado correctamente.")
            else:
                print("No se pudo eliminar el cliente.")

    except Exception as error:
        print(f"\nError al eliminar el cliente: {error}")

    input("\nPresione Enter para continuar...")
