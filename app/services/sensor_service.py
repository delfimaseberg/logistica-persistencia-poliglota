
from app.models.sensor_iot import SensorIoT

from app.repositories.lectura_iot_repository import (
    consultar_ultima_lectura_db
)

from app.repositories.sensor_repository import (
    crear_sensor,
    listar_sensores,
    buscar_sensor_por_id,
    listar_sensores_por_contenedor,
    actualizar_sensor,
    eliminar_sensor_db
)

from app.repositories.contenedor_repository import (
    buscar_contenedor_por_id,
    listar_contenedores
)

from app.utils.validaciones_sensor import (
    validar_tipo_sensor,
    validar_estado_sensor,
    validar_fabricante,
    validar_fecha_instalacion,
    validar_id_sensor,
    validar_id_contenedor
)
from app.utils import formato
from app.utils.errores import mensaje_error
from app.services.autenticacion import requiere_permiso


def pedir(mensaje, funcion):  # repite la pregunta hasta que la validación pase
    while True:
        try:
            return funcion(input(mensaje))
        except ValueError as error:
            print(f"Error: {mensaje_error(error)}")


def pausar():
    input("\nPresioná Enter para continuar...")


def mostrar_sensor(sensor):  # imprime los datos de un sensor; la usan las pantallas de sensores
    print("--------------------------------")
    print(f"ID sensor: {sensor[0]}")
    print(f"ID contenedor: {sensor[1]}")
    print(f"Código contenedor: {sensor[2]}")
    print(f"Tipo: {sensor[3]}")
    print(f"Fabricante: {sensor[4] or 'No especificado'}")
    print(f"Fecha de instalación: {formato.fecha(sensor[5]) if sensor[5] else 'No especificada'}")
    print(f"Estado: {sensor[6]}")


def pedir_contenedor():  # elige un contenedor que no esté inactivo; la usan alta y cambio de contenedor
    contenedores = listar_contenedores()

    if not contenedores:
        print("No hay contenedores registrados.")
        return None

    print("\n--- CONTENEDORES ---")

    for c in contenedores:
        print(
            f"ID: {c[0]} | "
            f"Código: {c[1]} | "
            f"Estado: {c[4]}"
        )

    while True:
        id_contenedor = pedir(
            "\nID del contenedor: ",
            validar_id_contenedor
        )

        contenedor = buscar_contenedor_por_id(id_contenedor)

        if contenedor is None:
            print("Error: no existe ese contenedor.")
            continue

        if contenedor[4] == "Inactivo":  # a un contenedor inactivo no se le ponen sensores
            print("Error: el contenedor está inactivo.")
            continue

        return id_contenedor


@requiere_permiso(1)
def registrar_sensor():  # da de alta un sensor en un contenedor; opción 6 del menú de contenedores
    print("\n--- REGISTRAR SENSOR IoT ---")

    try:
        id_contenedor = pedir_contenedor()

        if id_contenedor is None:
            return

        tipo = pedir(
            "Tipo (Temperatura/Humedad/GPS/Vibración/Apertura): ",
            validar_tipo_sensor
        )

        fabricante = pedir(
            "Fabricante (Enter si no corresponde): ",
            validar_fabricante
        )

        fecha = pedir(
            "Fecha de instalación AAAA-MM-DD (Enter si no corresponde): ",
            validar_fecha_instalacion
        )

        estado = pedir(
            "Estado (Activo/Inactivo/Mantenimiento): ",
            validar_estado_sensor
        )

        sensor = SensorIoT(
            id_contenedor,
            tipo,
            fabricante,
            fecha,
            estado
        )

        id_sensor = crear_sensor(sensor)  # INSERT en PostgreSQL; las lecturas van después a Cassandra

        print("\nSensor registrado correctamente.")
        print(f"ID generado: {id_sensor}")

        mostrar_sensor(buscar_sensor_por_id(id_sensor))

    except Exception as error:
        print(f"\nError al registrar sensor: {mensaje_error(error)}")

    finally:
        pausar()


@requiere_permiso(1)
def listar_sensores_service():  # lista todos los sensores; opción 7 del menú de contenedores
    print("\n--- LISTAR SENSORES ---")

    try:
        sensores = listar_sensores()

        if not sensores:
            print("No hay sensores registrados.")
            return

        print(f"\nTotal: {len(sensores)}")

        for sensor in sensores:
            mostrar_sensor(sensor)

    except Exception as error:
        print(f"\nError al listar sensores: {mensaje_error(error)}")

    finally:
        pausar()


@requiere_permiso(1)
def buscar_sensor_service():  # muestra un sensor por su ID; opción 8 del menú de contenedores
    print("\n--- BUSCAR SENSOR ---")

    try:
        id_sensor = pedir(
            "ID del sensor: ",
            validar_id_sensor
        )

        sensor = buscar_sensor_por_id(id_sensor)

        if sensor is None:
            print("No existe un sensor con ese ID.")
            return

        mostrar_sensor(sensor)

    except Exception as error:
        print(f"\nError al buscar sensor: {mensaje_error(error)}")

    finally:
        pausar()


@requiere_permiso(1)
def consultar_sensores_contenedor_service():  # sensores de un contenedor; opción 9 del menú de contenedores
    print("\n--- SENSORES DE UN CONTENEDOR ---")

    try:
        id_contenedor = pedir(
            "ID del contenedor: ",
            validar_id_contenedor
        )

        contenedor = buscar_contenedor_por_id(id_contenedor)

        if contenedor is None:
            print("No existe ese contenedor.")
            return

        sensores = listar_sensores_por_contenedor(
            id_contenedor
        )

        if not sensores:
            print("El contenedor no tiene sensores.")
            return

        print(f"\nTotal de sensores: {len(sensores)}")

        for sensor in sensores:
            mostrar_sensor(sensor)

    except Exception as error:
        print(f"\nError al consultar sensores: {mensaje_error(error)}")

    finally:
        pausar()


@requiere_permiso(1)
def modificar_sensor_service():  # cambia un dato del sensor; opción 10 del menú de contenedores
    print("\n--- MODIFICAR SENSOR ---")

    try:
        id_sensor = pedir(
            "ID del sensor: ",
            validar_id_sensor
        )

        actual = buscar_sensor_por_id(id_sensor)

        if actual is None:
            print("No existe un sensor con ese ID.")
            return

        print("\nDatos actuales:")
        mostrar_sensor(actual)

        print("\n¿Qué querés modificar?")
        print("1. Contenedor")
        print("2. Tipo")
        print("3. Fabricante")
        print("4. Fecha de instalación")
        print("5. Estado")
        print("0. Cancelar")

        opcion = input("Opción: ").strip()

        if opcion == "0":
            print("Modificación cancelada.")
            return

        if opcion not in ("1", "2", "3", "4", "5"):
            print("Opción inválida.")
            return

        id_contenedor = actual[1]
        tipo = actual[3]
        fabricante = actual[4]
        fecha = actual[5]
        estado = actual[6]

        if opcion == "1":
            ultima_lectura = consultar_ultima_lectura_db(id_sensor)  # pregunta a Cassandra: si ya tiene lecturas, no se cambia de contenedor

            if ultima_lectura is not None:
                print(
                    "\nNo se puede cambiar el contenedor "
                    "de un sensor que ya tiene lecturas."
                )
                print(
                    "Para conservar la trazabilidad, "
                    "da de baja este sensor y registrá uno nuevo."
                )
                return

            nuevo_contenedor = pedir_contenedor()

            if nuevo_contenedor is None:
                return

            id_contenedor = nuevo_contenedor


        elif opcion == "2":
            ultima_lectura = consultar_ultima_lectura_db(id_sensor)  # ni de tipo, para no mezclar el historial

            if ultima_lectura is not None:
                print(
                    "\nNo se puede cambiar el tipo "
                    "de un sensor que ya tiene lecturas."
                )
                print(
                    "Da de baja este sensor y registrá "
                    "otro con el nuevo tipo."
                )
                return

            tipo = pedir(
                "Nuevo tipo: ",
                validar_tipo_sensor
            )


        elif opcion == "3":
            fabricante = pedir(
                "Nuevo fabricante (Enter para dejar vacío): ",
                validar_fabricante
            )

        elif opcion == "4":
            fecha = pedir(
                "Nueva fecha AAAA-MM-DD (Enter para dejar vacía): ",
                validar_fecha_instalacion
            )

        elif opcion == "5":
            estado = pedir(
                "Nuevo estado (Activo/Inactivo/Mantenimiento): ",
                validar_estado_sensor
            )

        actualizado = SensorIoT(
            id_contenedor,
            tipo,
            fabricante,
            fecha,
            estado
        )

        if actualizar_sensor(id_sensor, actualizado):  # UPDATE en PostgreSQL
            print("\nSensor modificado correctamente.")
            mostrar_sensor(
                buscar_sensor_por_id(id_sensor)
            )
        else:
            print("No se pudo modificar el sensor.")

    except Exception as error:
        print(f"\nError al modificar sensor: {mensaje_error(error)}")

    finally:
        pausar()


@requiere_permiso(1)
def eliminar_sensor_service():  # da de baja un sensor (no lo borra); opción 11 del menú de contenedores
    print("\n--- DAR DE BAJA SENSOR ---")

    try:
        id_sensor = pedir(
            "ID del sensor: ",
            validar_id_sensor
        )

        sensor = buscar_sensor_por_id(id_sensor)

        if sensor is None:
            print("No existe un sensor con ese ID.")
            return

        print("\nDatos del sensor:")
        mostrar_sensor(sensor)

        if str(sensor[6]).strip().lower() == "inactivo":
            print("\nEl sensor ya se encuentra inactivo.")
            return

        print(
            "\nEl sensor no se borrará de la base de datos."
            "\nSu estado cambiará a Inactivo."
            "\nSus lecturas históricas se conservan."
        )

        confirmacion = input(
            "\n¿Confirmar baja del sensor? (S/N): "
        ).strip().upper()

        if confirmacion != "S":
            print("\nOperación cancelada.")
            return

        if eliminar_sensor_db(id_sensor):  # pasa a Inactivo y las lecturas de Cassandra se conservan
            print("\nSensor dado de baja correctamente.")
            print("Estado actual: Inactivo")
        else:
            print("\nNo se pudo dar de baja el sensor.")

    except Exception as error:
        print(f"\nError al dar de baja el sensor: {mensaje_error(error)}")

    finally:
        pausar()