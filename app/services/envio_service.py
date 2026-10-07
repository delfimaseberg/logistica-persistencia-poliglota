from app.models.envio import Envio
from app.models.tramo import Tramo
from app.utils.validaciones import (
    texto_obligatorio,
    validar_entero_positivo,
    validar_opcion
)


def pedir_dato(mensaje, validador, *args):
    while True:
        try:
            return validador(input(mensaje), *args)
        except ValueError as error:
            print(f"Error: {error}")


def registrar_envio():
    print("\n--- REGISTRAR ENVÍO ---")

    id_cliente = pedir_dato(
        "ID del cliente: ",
        validar_entero_positivo,
        "El ID del cliente"
    )

    origen = pedir_dato(
        "Origen: ",
        texto_obligatorio,
        "El origen"
    )

    destino = pedir_dato(
        "Destino: ",
        texto_obligatorio,
        "El destino"
    )

    estado = pedir_dato(
        "Estado (Pendiente/En tránsito/Entregado/Cancelado): ",
        validar_opcion,
        ["Pendiente", "En tránsito", "Entregado", "Cancelado"],
        "El estado"
    )

    prioridad = pedir_dato(
        "Prioridad (Baja/Media/Alta): ",
        validar_opcion,
        ["Baja", "Media", "Alta"],
        "La prioridad"
    )

    envio = Envio(
        id_cliente,
        origen,
        destino,
        estado,
        prioridad
    )

    print("\nEnvío ingresado correctamente:")
    print("--------------------------------")
    print(envio)

    input("\nPresione Enter para continuar...")


def registrar_tramo():
    print("\n--- REGISTRAR TRAMO ---")

    id_envio = pedir_dato(
        "ID del envío: ",
        validar_entero_positivo,
        "El ID del envío"
    )

    id_vehiculo = pedir_dato(
        "ID del vehículo: ",
        validar_entero_positivo,
        "El ID del vehículo"
    )

    medio_transporte = pedir_dato(
        "Medio de transporte (Terrestre/Marítimo/Aéreo): ",
        validar_opcion,
        ["Terrestre", "Marítimo", "Aéreo"],
        "El medio de transporte"
    )

    origen = pedir_dato(
        "Origen: ",
        texto_obligatorio,
        "El origen"
    )

    destino = pedir_dato(
        "Destino: ",
        texto_obligatorio,
        "El destino"
    )

    fecha_salida = pedir_dato(
        "Fecha de salida (AAAA-MM-DD): ",
        texto_obligatorio,
        "La fecha de salida"
    )

    fecha_estimada_llegada = pedir_dato(
        "Fecha estimada de llegada (AAAA-MM-DD): ",
        texto_obligatorio,
        "La fecha estimada de llegada"
    )

    tramo = Tramo(
        id_envio,
        id_vehiculo,
        medio_transporte,
        origen,
        destino,
        fecha_salida,
        fecha_estimada_llegada
    )

    print("\nTramo ingresado correctamente:")
    print("--------------------------------")
    print(tramo)

    input("\nPresione Enter para continuar...")