from app.models.tramo import Tramo

from app.repositories.envio_repository import buscar_envio_por_id
from app.repositories.vehiculo_repository import (
    listar_vehiculos,
    buscar_vehiculo_por_id
)
from app.repositories.tramo_repository import (
    crear_tramo,
    listar_tramos_de_envio
)

from app.utils.validaciones_logistica import (
    validar_texto,
    validar_fecha,
    validar_rango_fechas,
    validar_entero_positivo_logistica,
    normalizar
)

from app.services.sincronizacion_service import sincronizar_envio_neo4j


def pedir(mensaje, funcion, *args):
    while True:
        try:
            return funcion(input(mensaje), *args)
        except ValueError as error:
            print(f"Error: {error}")


def pausar():
    input("\nPresione Enter para continuar...")


def pedir_ubicacion(mensaje, valor_sugerido=None):
    while True:
        if valor_sugerido:
            valor = input(
                f"{mensaje} [{valor_sugerido}]: "
            ).strip()

            if not valor:
                valor = valor_sugerido
        else:
            valor = input(f"{mensaje}: ").strip()

        try:
            return validar_texto(valor, mensaje, 150)
        except ValueError as error:
            print(f"Error: {error}")


def registrar_tramo():
    print("\n--- REGISTRAR TRAMO ---")

    try:
        id_envio = pedir(
            "ID del envío: ",
            validar_entero_positivo_logistica,
            "El ID del envío"
        )

        envio = buscar_envio_por_id(id_envio)

        if envio is None:
            print("No existe un envío con ese ID.")
            return

        if normalizar(envio[5]) in ("cancelado", "entregado"):
            print(
                "No se pueden agregar tramos a un envío "
                "cancelado o entregado."
            )
            return

        tramos_existentes = listar_tramos_de_envio(id_envio)

        print("\n--- DATOS DEL ENVÍO ---")
        print(f"Cliente: {envio[2]}")
        print(f"Origen general: {envio[3]}")
        print(f"Destino final: {envio[4]}")

        if tramos_existentes:
            print("\nTramos registrados:")

            for numero, tramo in enumerate(
                tramos_existentes, start=1
            ):
                print(
                    f"{numero}. {tramo[5]} → {tramo[6]} "
                    f"({tramo[4]})"
                )

            ultimo_tramo = tramos_existentes[-1]
            origen_sugerido = ultimo_tramo[6]

            print(
                "\nSe sugiere continuar desde el destino "
                "del último tramo registrado."
            )

        else:
            origen_sugerido = envio[3]

            print(
                "\nEste es el primer tramo del envío. "
                "Se sugiere comenzar desde su origen."
            )

        vehiculos = listar_vehiculos()

        disponibles = [
            v for v in vehiculos
            if normalizar(v[4]) == "disponible"
        ]

        if not disponibles:
            print(
                "\nNo hay vehículos disponibles. "
                "Primero registre uno."
            )
            return

        print("\n--- VEHÍCULOS DISPONIBLES ---")

        for vehiculo in disponibles:
            print(
                f"ID: {vehiculo[0]} | "
                f"Tipo: {vehiculo[1]} | "
                f"Identificación: {vehiculo[2]}"
            )

        while True:
            id_vehiculo = pedir(
                "\nID del vehículo: ",
                validar_entero_positivo_logistica,
                "El ID del vehículo"
            )

            vehiculo = buscar_vehiculo_por_id(id_vehiculo)

            if vehiculo is None:
                print("El vehículo no existe.")
                continue

            if normalizar(vehiculo[4]) != "disponible":
                print("El vehículo no está disponible.")
                continue

            break

        # El medio se obtiene automáticamente del vehículo.
        medio = vehiculo[1]

        print("\nVehículo seleccionado:")
        print(f"Identificación: {vehiculo[2]}")
        print(f"Medio de transporte: {medio} (automático)")

        # El origen continúa el recorrido registrado.
        origen = origen_sugerido

        print(f"\nOrigen del tramo: {origen} (automático)")

        destino = pedir_ubicacion(
            "Destino del tramo",
            envio[4]
        )

        if normalizar(origen) == normalizar(destino):
            print(
                "\nError: el origen y destino del tramo "
                "no pueden ser iguales."
            )
            return

        # No permitir nuevos tramos si ya se llegó al destino final.
        if tramos_existentes:
            if normalizar(ultimo_tramo[6]) == normalizar(envio[4]):
                print(
                    "\nEl recorrido ya llegó al destino final. "
                    "No se pueden agregar más tramos."
                )
                return

        while True:
            fecha_salida = pedir(
                "Fecha de salida (AAAA-MM-DD): ",
                validar_fecha,
                "La fecha de salida"
            )

            fecha_llegada = pedir(
                "Fecha estimada de llegada (AAAA-MM-DD): ",
                validar_fecha,
                "La fecha estimada de llegada"
            )

            try:
                validar_rango_fechas(
                    fecha_salida,
                    fecha_llegada
                )

                if tramos_existentes:
                    ultima_llegada = ultimo_tramo[8]

                    if fecha_salida < ultima_llegada:
                        print(
                            "Error: el nuevo tramo no puede "
                            "salir antes de la llegada estimada "
                            "del tramo anterior."
                        )
                        continue

                break

            except ValueError as error:
                print(f"Error: {error}")

        tramo = Tramo(
            id_envio,
            id_vehiculo,
            medio,
            origen,
            destino,
            fecha_salida,
            fecha_llegada
        )

        print("\n--- RESUMEN DEL TRAMO ---")
        print(f"Envío: {id_envio}")
        print(f"Vehículo: {vehiculo[2]}")
        print(f"Medio: {medio}")
        print(f"Origen: {origen}")
        print(f"Destino: {destino}")
        print(f"Salida: {fecha_salida.date()}")
        print(f"Llegada estimada: {fecha_llegada.date()}")

        confirmacion = input(
            "\n¿Confirmar registro? (S/N): "
        ).strip().upper()

        if confirmacion != "S":
            print("Registro cancelado.")
            return

        id_tramo = crear_tramo(tramo)

        print("\nTramo registrado correctamente.")
        print(f"ID generado: {id_tramo}")

        # Sincronizar el nuevo tramo con Neo4j.
        # Se ejecuta después de guardar correctamente en PostgreSQL.
        sincronizar_envio_neo4j(id_envio)

        if normalizar(destino) == normalizar(envio[4]):
            print(
                "Este tramo llega al destino final del envío."
            )

    except Exception as error:
        print(f"\nError al registrar el tramo: {error}")

    finally:
        pausar()


def consultar_tramos_service():
    print("\n--- CONSULTAR TRAMOS DE UN ENVÍO ---")

    try:
        id_envio = pedir(
            "ID del envío: ",
            validar_entero_positivo_logistica,
            "El ID del envío"
        )

        envio = buscar_envio_por_id(id_envio)

        if envio is None:
            print("No existe un envío con ese ID.")
            return

        tramos = listar_tramos_de_envio(id_envio)

        print(f"\nEnvío: {id_envio}")
        print(f"Origen general: {envio[3]}")
        print(f"Destino final: {envio[4]}")

        if not tramos:
            print("\nEste envío todavía no tiene tramos.")
            return

        print(f"\nTotal de tramos: {len(tramos)}")

        for numero, tramo in enumerate(tramos, start=1):
            print("\n--------------------------------")
            print(f"Tramo {numero} - ID: {tramo[0]}")
            print(f"Vehículo: {tramo[3]} (ID {tramo[2]})")
            print(f"Medio: {tramo[4]}")
            print(f"Origen: {tramo[5]}")
            print(f"Destino: {tramo[6]}")
            print(f"Salida: {tramo[7]}")
            print(f"Llegada estimada: {tramo[8]}")

    except Exception as error:
        print(f"Error al consultar tramos: {error}")

    finally:
        pausar()