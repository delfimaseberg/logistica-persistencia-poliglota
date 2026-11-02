from app.models.envio import Envio

from app.repositories.envio_repository import (
    obtener_clientes,
    obtener_cliente_por_id,
    crear_envio,
    listar_envios,
    buscar_envio_por_id,
    actualizar_envio,
    actualizar_paises_envio,
    eliminar_envio_db
)

from app.utils.validaciones import (
    texto_obligatorio,
    validar_entero_positivo,
    validar_opcion
)

from app.services.sincronizacion_service import sincronizar_envio_neo4j
from app.utils import formato
from app.utils.errores import mensaje_error
from app.utils.validaciones_datos import validar_largo
from app.services.autenticacion import requiere_permiso


ESTADOS = [
    "Pendiente",
    "En tránsito",
    "Entregado",
    "Cancelado"
]

# Entregado solo se alcanza registrando el evento ENTREGADO en Trazabilidad,
# que guarda la fecha real de entrega. No se elige a mano.
ESTADOS_EDITABLES = [
    "Pendiente",
    "En tránsito",
    "Cancelado"
]

MENSAJE_ENTREGA = (
    "Para marcar un envío como Entregado registrá el evento ENTREGADO en "
    "Trazabilidad (guarda la fecha real de entrega)."
)


def es_entregado(estado):
    return str(estado or "").strip().casefold() == "entregado"


PRIORIDADES = [
    "Baja",
    "Media",
    "Alta"
]


def pedir_dato(mensaje, validador, *args):
    while True:
        try:
            return validador(input(mensaje), *args)
        except ValueError as error:
            print(f"Error: {mensaje_error(error)}")


def pausar():
    input("\nPresioná Enter para continuar...")


def mostrar_envio(envio):
    print("--------------------------------")
    print(f"ID envío: {envio[0]}")
    print(f"ID cliente: {envio[1]}")
    print(f"Cliente: {envio[2]}")
    pais_origen = envio[9] if len(envio) > 9 and envio[9] else "sin dato"
    pais_destino = envio[10] if len(envio) > 10 and envio[10] else "sin dato"
    print(f"Origen: {envio[3]} ({pais_origen})")
    print(f"Destino: {envio[4]} ({pais_destino})")
    print(f"Estado: {envio[5]}")
    print(f"Prioridad: {envio[6]}")
    print(f"Fecha de creación: {formato.fecha_hora(envio[7])}")
    if len(envio) > 8 and envio[8] is not None:
        print(f"Fecha real de entrega: {formato.fecha_hora(envio[8])}")


def seleccionar_cliente():
    clientes = obtener_clientes()

    if not clientes:
        print("\nNo hay clientes registrados.")
        print("Primero debés registrar un cliente.")
        return None

    print("\n--- CLIENTES DISPONIBLES ---")

    for cliente in clientes:
        print(
            f"ID: {cliente[0]} | "
            f"Razón social: {cliente[1]} | "
            f"CUIT: {cliente[2]}"
        )

    while True:
        id_cliente = pedir_dato(
            "\nIngresá el ID del cliente: ",
            validar_entero_positivo,
            "El ID del cliente"
        )

        cliente = obtener_cliente_por_id(id_cliente)

        if cliente is not None:
            return id_cliente

        print("No existe un cliente con ese ID.")


@requiere_permiso(1)
def registrar_envio():
    print("\n--- REGISTRAR ENVÍO ---")

    try:
        id_cliente = seleccionar_cliente()

        if id_cliente is None:
            return

        origen = pedir_dato(
            "Origen: ",
            validar_largo,
            "El origen", 150
        )

        pais_origen = pedir_dato(
            "País de origen: ",
            validar_largo,
            "El país de origen", 80
        )

        destino = pedir_dato(
            "Destino: ",
            validar_largo,
            "El destino", 150
        )

        pais_destino = pedir_dato(
            "País de destino: ",
            validar_largo,
            "El país de destino", 80
        )

        estado = pedir_dato(
            "Estado (Pendiente/En tránsito/Cancelado): ",
            validar_opcion,
            ESTADOS_EDITABLES,
            "El estado"
        )

        prioridad = pedir_dato(
            "Prioridad (Baja/Media/Alta): ",
            validar_opcion,
            PRIORIDADES,
            "La prioridad"
        )

        envio = Envio(
            id_cliente,
            origen,
            destino,
            estado,
            prioridad,
            pais_origen=pais_origen,
            pais_destino=pais_destino
        )

        id_envio = crear_envio(envio)

        # Sincronizar el nuevo envío con Neo4j.
        sincronizar_envio_neo4j(id_envio)

        print("\nEnvío registrado correctamente.")
        print(f"ID del envío generado: {id_envio}")

        envio_guardado = buscar_envio_por_id(id_envio)

        if envio_guardado:
            mostrar_envio(envio_guardado)

    except Exception as error:
        print(f"\nError al registrar el envío: {mensaje_error(error)}")

    finally:
        pausar()


@requiere_permiso(1)
def listar_envios_service():
    print("\n--- LISTAR ENVÍOS ---")

    try:
        envios = listar_envios()

        if not envios:
            print("No hay envíos registrados.")
            return

        print(f"\nTotal de envíos: {len(envios)}")

        for envio in envios:
            mostrar_envio(envio)

    except Exception as error:
        print(f"\nError al listar envíos: {mensaje_error(error)}")

    finally:
        pausar()


@requiere_permiso(1)
def buscar_envio_service():
    print("\n--- BUSCAR ENVÍO ---")

    try:
        id_envio = pedir_dato(
            "Ingresá el ID del envío: ",
            validar_entero_positivo,
            "El ID del envío"
        )

        envio = buscar_envio_por_id(id_envio)

        if envio is None:
            print("\nNo se encontró un envío con ese ID.")
            return

        mostrar_envio(envio)

    except Exception as error:
        print(f"\nError al buscar el envío: {mensaje_error(error)}")

    finally:
        pausar()


@requiere_permiso(1)
def modificar_envio_service():
    print("\n--- MODIFICAR ENVÍO ---")

    try:
        id_envio = pedir_dato(
            "Ingresá el ID del envío a modificar: ",
            validar_entero_positivo,
            "El ID del envío"
        )

        envio_actual = buscar_envio_por_id(id_envio)

        if envio_actual is None:
            print("\nNo se encontró un envío con ese ID.")
            return

        print("\nDatos actuales del envío:")
        mostrar_envio(envio_actual)

        print("\nSeleccioná qué dato querés modificar:")
        print("1. Cliente")
        print("2. Origen")
        print("3. Destino")
        print("4. Estado")
        print("5. Prioridad")
        print("6. Países de origen y destino")
        print("0. Cancelar")

        opcion = input("\nOpción: ").strip()

        if opcion == "0":
            print("Modificación cancelada.")
            return

        if opcion not in ["1", "2", "3", "4", "5", "6"]:
            print("Opción inválida.")
            return

        # Países: se pueden completar o corregir en cualquier estado
        # (los envíos anteriores a la migración 014 no los tienen).
        if opcion == "6":
            pais_origen = pedir_dato(
                "País de origen: ", validar_largo, "El país de origen", 80
            )
            pais_destino = pedir_dato(
                "País de destino: ", validar_largo, "El país de destino", 80
            )
            if actualizar_paises_envio(id_envio, pais_origen, pais_destino):
                print("\nPaíses actualizados.")
                mostrar_envio(buscar_envio_por_id(id_envio))
            else:
                print("\nNo se pudieron actualizar los países.")
            return

        # Entregado es final: solo se puede cambiar la prioridad (los
        # países se resolvieron antes).
        if es_entregado(envio_actual[5]) and opcion not in ("5", "6"):
            print(
                "\nEl envío está Entregado: su cliente, ruta y estado ya no "
                "se modifican."
            )
            return

        id_cliente = envio_actual[1]
        origen = envio_actual[3]
        destino = envio_actual[4]
        estado = envio_actual[5]
        prioridad = envio_actual[6]

        if opcion == "1":
            nuevo_cliente = seleccionar_cliente()

            if nuevo_cliente is None:
                return

            id_cliente = nuevo_cliente

        elif opcion == "2":
            origen = pedir_dato(
                "Nuevo origen: ",
                validar_largo,
                "El origen", 150
            )

        elif opcion == "3":
            destino = pedir_dato(
                "Nuevo destino: ",
                validar_largo,
                "El destino", 150
            )

        elif opcion == "4":
            print(MENSAJE_ENTREGA)
            estado = pedir_dato(
                "Nuevo estado (Pendiente/En tránsito/Cancelado): ",
                validar_opcion,
                ESTADOS_EDITABLES,
                "El estado"
            )

        elif opcion == "5":
            prioridad = pedir_dato(
                "Nueva prioridad (Baja/Media/Alta): ",
                validar_opcion,
                PRIORIDADES,
                "La prioridad"
            )

        # No alterar extremos de una ruta que ya tiene tramos registrados.
        if opcion in ("2", "3") and (
            origen != envio_actual[3] or destino != envio_actual[4]
        ):
            from app.repositories.tramo_repository import listar_tramos_de_envio

            if listar_tramos_de_envio(id_envio):
                print(
                    "\nNo se puede cambiar el origen o destino: "
                    "el envío ya tiene tramos registrados."
                )
                return

        envio_modificado = Envio(
            id_cliente,
            origen,
            destino,
            estado,
            prioridad
        )

        actualizado = actualizar_envio(
            id_envio,
            envio_modificado
        )

        if actualizado:
            # Sincronizar los cambios del envío con Neo4j.
            sincronizar_envio_neo4j(id_envio)

            print("\nEnvío modificado correctamente.")

            envio_actualizado = buscar_envio_por_id(id_envio)

            if envio_actualizado:
                mostrar_envio(envio_actualizado)
        else:
            print("\nNo se pudo modificar el envío.")

    except Exception as error:
        print(f"\nError al modificar el envío: {mensaje_error(error)}")

    finally:
        pausar()


@requiere_permiso(1)
def eliminar_envio_service():
    print("\n--- ELIMINAR ENVÍO ---")

    try:
        id_envio = pedir_dato(
            "Ingresá el ID del envío a eliminar: ",
            validar_entero_positivo,
            "El ID del envío"
        )

        envio = buscar_envio_por_id(id_envio)

        if envio is None:
            print("\nNo se encontró un envío con ese ID.")
            return

        print("\nEnvío seleccionado:")
        mostrar_envio(envio)

        if es_entregado(envio[5]):
            print(
                "\nUn envío Entregado no se elimina: es la base de su "
                "facturación y de la de sus operadores."
            )
            return

        confirmacion = input(
            "\n¿Seguro que querés eliminar este envío? (S/N): "
        ).strip().upper()

        if confirmacion != "S":
            print("Eliminación cancelada.")
            return

        eliminado = eliminar_envio_db(id_envio)

        if eliminado:
            # El envío ya no existe en PostgreSQL.
            # La sincronización elimina su proyección de Neo4j.
            sincronizar_envio_neo4j(id_envio)

            print("\nEnvío eliminado correctamente.")
        else:
            print("\nNo se pudo eliminar el envío.")

    except Exception as error:
        print(f"\nError al eliminar el envío: {mensaje_error(error)}")
        print(
            "Si el envío tiene tramos, incidentes o contenedores "
            "asociados, el sistema puede impedir su eliminación."
        )

    finally:
        pausar()