from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from math import isfinite

from app.repositories.sensor_repository import (
    buscar_sensor_por_id
)

from app.repositories.contenedor_repository import (
    buscar_contenedor_por_id
)

from app.repositories.lectura_iot_repository import (
    registrar_lectura_db,
    consultar_lecturas_sensor_db,
    consultar_lecturas_contenedor_db,
    consultar_ultima_lectura_db
)


def pausar():
    input("\nPresione Enter para continuar...")


def pedir_id(mensaje):
    while True:
        try:
            valor = int(input(mensaje).strip())

            if valor <= 0:
                raise ValueError

            return valor

        except ValueError:
            print("Error: ingrese un ID entero positivo.")


def pedir_decimal(mensaje, minimo=None, maximo=None):
    while True:
        try:
            texto = input(mensaje).strip().replace(",", ".")
            valor = float(texto)

            if not isfinite(valor):
                raise ValueError

            if minimo is not None and valor < minimo:
                print(f"Error: el mínimo permitido es {minimo}.")
                continue

            if maximo is not None and valor > maximo:
                print(f"Error: el máximo permitido es {maximo}.")
                continue

            return valor

        except ValueError:
            print("Error: ingrese un número válido.")


def pedir_bateria():
    texto = input(
        "Batería (%) (Enter si no se conoce): "
    ).strip()

    if not texto:
        return None

    while True:
        try:
            valor = float(texto.replace(",", "."))

            if not isfinite(valor) or not 0 <= valor <= 100:
                raise ValueError

            return valor

        except ValueError:
            print("Error: ingrese un valor entre 0 y 100.")
            texto = input("Batería (%): ").strip()

            if not texto:
                return None


def pedir_anio_mes():
    while True:
        valor = input(
            "Mes (AAAA-MM, Enter = mes actual): "
        ).strip()

        if not valor:
            return datetime.now().strftime("%Y-%m")

        try:
            fecha = datetime.strptime(valor, "%Y-%m")

            if fecha.strftime("%Y-%m") != valor:
                raise ValueError

            return valor

        except ValueError:
            print("Error: formato inválido. Ejemplo: 2026-10.")


def mostrar_lectura(lectura):
    print("--------------------------------")

    fecha_utc = lectura.fecha_hora

    if fecha_utc.tzinfo is None:
        fecha_utc = fecha_utc.replace(tzinfo=timezone.utc)

    fecha_argentina = fecha_utc.astimezone(
        ZoneInfo("America/Argentina/Buenos_Aires")
    )

    print(
        "Fecha (Argentina): "
        f"{fecha_argentina.strftime('%d/%m/%Y %H:%M:%S')}"
    )

    print(f"ID lectura: {lectura.id_lectura}")

    campos = [
        ("Temperatura", "temperatura", "°C"),
        ("Humedad", "humedad", "%"),
        ("Vibración", "vibracion", ""),
        ("Latitud GPS", "gps_latitud", ""),
        ("Longitud GPS", "gps_longitud", ""),
        ("Batería", "bateria", "%")
    ]

    for etiqueta, atributo, unidad in campos:
        valor = getattr(lectura, atributo, None)

        if valor is not None:
            print(f"{etiqueta}: {valor} {unidad}".rstrip())


def registrar_lectura_service():
    print("\n--- REGISTRAR LECTURA IoT ---")

    try:
        id_sensor = pedir_id("ID del sensor: ")
        sensor = buscar_sensor_por_id(id_sensor)

        if sensor is None:
            print("\nNo existe ese sensor.")
            return

        id_contenedor = sensor[1]
        tipo = str(sensor[3]).strip().lower()
        estado = str(sensor[6]).strip().lower()

        if estado != "activo":
            print("\nEl sensor no está activo.")
            return

        contenedor = buscar_contenedor_por_id(id_contenedor)

        if contenedor is None:
            print("\nEl contenedor asociado no existe.")
            return

        if str(contenedor[4]).strip().lower() == "inactivo":
            print("\nEl contenedor está inactivo.")
            return

        print(f"\nSensor: {sensor[0]}")
        print(f"Tipo: {sensor[3]}")
        print(f"Contenedor: {sensor[2]}")

        temperatura = None
        humedad = None
        vibracion = None
        gps_latitud = None
        gps_longitud = None

        if tipo == "temperatura":
            temperatura = pedir_decimal("Temperatura (°C): ")

        elif tipo == "humedad":
            humedad = pedir_decimal("Humedad (%): ", 0, 100)

        elif tipo in ("vibración", "vibracion"):
            vibracion = pedir_decimal(
                "Vibración (valor no negativo): ", 0
            )

        elif tipo == "gps":
            gps_latitud = pedir_decimal(
                "Latitud GPS: ", -90, 90
            )
            gps_longitud = pedir_decimal(
                "Longitud GPS: ", -180, 180
            )

        elif tipo == "apertura":
            print(
                "\nEl esquema actual de Cassandra no tiene "
                "un campo para el estado de apertura."
            )
            print("No se registrará esta lectura.")
            return

        else:
            print("\nTipo de sensor no reconocido.")
            return

        bateria = pedir_bateria()

        id_lectura = registrar_lectura_db(
            id_sensor=id_sensor,
            id_contenedor=id_contenedor,
            temperatura=temperatura,
            humedad=humedad,
            vibracion=vibracion,
            gps_latitud=gps_latitud,
            gps_longitud=gps_longitud,
            bateria=bateria
        )

        print("\nLectura IoT registrada correctamente.")
        print(f"ID lectura: {id_lectura}")
        print(f"Sensor: {id_sensor}")
        print(f"Contenedor: {id_contenedor}")

    except Exception as error:
        print(f"\nError al registrar la lectura: {error}")

    finally:
        pausar()


def consultar_lecturas_sensor_service():
    print("\n--- CONSULTAR LECTURAS POR SENSOR ---")

    try:
        id_sensor = pedir_id("ID del sensor: ")
        anio_mes = pedir_anio_mes()

        lecturas = consultar_lecturas_sensor_db(
            id_sensor, anio_mes
        )

        if not lecturas:
            print("\nNo se encontraron lecturas.")
            return

        print(f"\nSensor: {id_sensor}")
        print(f"Mes: {anio_mes}")
        print(f"Lecturas encontradas: {len(lecturas)}")

        for lectura in lecturas:
            mostrar_lectura(lectura)

    except Exception as error:
        print(f"\nError al consultar lecturas: {error}")

    finally:
        pausar()


def consultar_lecturas_contenedor_service():
    print("\n--- CONSULTAR LECTURAS POR CONTENEDOR ---")

    try:
        id_contenedor = pedir_id("ID del contenedor: ")
        anio_mes = pedir_anio_mes()

        lecturas = consultar_lecturas_contenedor_db(
            id_contenedor, anio_mes
        )

        if not lecturas:
            print("\nNo se encontraron lecturas.")
            return

        print(f"\nContenedor: {id_contenedor}")
        print(f"Mes: {anio_mes}")
        print(f"Lecturas encontradas: {len(lecturas)}")

        for lectura in lecturas:
            print(f"\nSensor: {lectura.sensor_id}")
            mostrar_lectura(lectura)

    except Exception as error:
        print(f"\nError al consultar lecturas: {error}")

    finally:
        pausar()


def consultar_ultima_lectura_service():
    print("\n--- ÚLTIMA LECTURA DE UN SENSOR ---")

    try:
        id_sensor = pedir_id("ID del sensor: ")

        lectura = consultar_ultima_lectura_db(id_sensor)

        if lectura is None:
            print("\nNo hay lecturas registradas.")
            return

        print(f"\nSensor: {id_sensor}")
        print(f"Contenedor: {lectura.contenedor_id}")

        mostrar_lectura(lectura)

    except Exception as error:
        print(f"\nError al consultar la última lectura: {error}")

    finally:
        pausar()