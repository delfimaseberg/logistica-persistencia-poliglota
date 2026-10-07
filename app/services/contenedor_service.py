from app.models.contenedor import Contenedor
from app.models.sensor import Sensor
from app.utils.validaciones import (
    texto_obligatorio,
    validar_entero_positivo,
    validar_numero_positivo,
    validar_fecha
)


def pedir_dato(mensaje, validador, *args):
    while True:
        try:
            return validador(input(mensaje), *args)
        except ValueError as error:
            print(f"Error: {error}")


def registrar_contenedor():
    print("\n--- REGISTRAR CONTENEDOR ---")

    codigo_internacional = pedir_dato(
        "Código internacional: ",
        texto_obligatorio,
        "El código internacional"
    )

    tipo = pedir_dato(
        "Tipo: ",
        texto_obligatorio,
        "El tipo"
    )

    capacidad = pedir_dato(
        "Capacidad: ",
        validar_numero_positivo,
        "La capacidad"
    )

    estado = pedir_dato(
        "Estado: ",
        texto_obligatorio,
        "El estado"
    )

    contenedor = Contenedor(
        codigo_internacional,
        tipo,
        capacidad,
        estado
    )

    print("\nContenedor ingresado correctamente:")
    print("------------------------------------")
    print(contenedor)

    input("\nPresione Enter para continuar...")


def registrar_sensor():
    print("\n--- REGISTRAR SENSOR IoT ---")

    id_contenedor = pedir_dato(
        "ID del contenedor: ",
        validar_entero_positivo,
        "El ID del contenedor"
    )

    tipo = pedir_dato(
        "Tipo de sensor: ",
        texto_obligatorio,
        "El tipo de sensor"
    )

    fabricante = pedir_dato(
        "Fabricante: ",
        texto_obligatorio,
        "El fabricante"
    )

    fecha_instalacion = pedir_dato(
        "Fecha de instalación (AAAA-MM-DD): ",
        validar_fecha
    )

    estado = pedir_dato(
        "Estado: ",
        texto_obligatorio,
        "El estado"
    )

    sensor = Sensor(
        id_contenedor,
        tipo,
        fabricante,
        fecha_instalacion.strftime("%Y-%m-%d"),
        estado
    )

    print("\nSensor ingresado correctamente:")
    print("-------------------------------")
    print(sensor)

    input("\nPresione Enter para continuar...")