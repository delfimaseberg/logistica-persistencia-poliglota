from app.repositories.envio_repository import buscar_envio_por_id

from app.repositories.contenedor_repository import (
    listar_contenedores_disponibles,
    buscar_contenedor_por_id
)

from app.repositories.envio_contenedor_repository import (
    asociar_contenedor_db,
    listar_contenedores_de_envio,
    buscar_asociacion,
    desasociar_contenedor_db
)

from app.utils.validaciones_logistica import (
    validar_entero_positivo_logistica
)

from app.services.sincronizacion_service import sincronizar_envio_neo4j
from app.utils.errores import mensaje_error
from app.utils import formato
from app.services.autenticacion import requiere_permiso


def pedir_id(mensaje, nombre):  # pide un ID entero positivo
    while True:
        try:
            return validar_entero_positivo_logistica(
                input(mensaje), nombre
            )
        except ValueError as error:
            print(f"Error: {mensaje_error(error)}")


def pausar():
    input("\nPresioná Enter para continuar...")


@requiere_permiso(1)
def asociar_contenedor_service():  # asigna un contenedor libre a un envío; opción 9 del menú de envíos
    print("\n--- ASOCIAR CONTENEDOR A ENVÍO ---")

    try:
        id_envio = pedir_id(
            "ID del envío: ",
            "El ID del envío"
        )

        envio = buscar_envio_por_id(id_envio)

        if envio is None:
            print("No existe un envío con ese ID.")
            return

        if envio[5] in ("Cancelado", "Entregado"):  # a un envío cerrado no se le agregan contenedores
            print(
                "No se pueden asociar contenedores "
                "a un envío cancelado o entregado."
            )
            return

        disponibles = listar_contenedores_disponibles()  # solo los Disponibles sin otro envío

        if not disponibles:
            print(
                "No hay contenedores disponibles "
                "sin asignaciones."
            )
            return

        print("\n--- CONTENEDORES DISPONIBLES ---")

        for contenedor in disponibles:
            print(
                f"ID: {contenedor[0]} | "
                f"Código: {contenedor[1]} | "
                f"Tipo: {contenedor[2]} | "
                f"Capacidad: {formato.compacto(contenedor[3])} t"
            )

        id_contenedor = pedir_id(
            "\nID del contenedor: ",
            "El ID del contenedor"
        )

        contenedor = buscar_contenedor_por_id(id_contenedor)

        if contenedor is None:
            print("No existe un contenedor con ese ID.")
            return

        if buscar_asociacion(id_envio, id_contenedor):
            print("Ese contenedor ya está asociado al envío.")
            return

        print("\nEnvío seleccionado:")
        print(f"ID: {envio[0]}")
        print(f"Origen: {envio[3]}")
        print(f"Destino: {envio[4]}")

        print("\nContenedor seleccionado:")
        print(f"Código: {contenedor[1]}")
        print(f"Tipo: {contenedor[2]}")

        confirmar = input(
            "\n¿Confirmar asociación? (S/N): "
        ).strip().upper()

        if confirmar != "S":
            print("Operación cancelada.")
            return

        if asociar_contenedor_db(id_envio, id_contenedor):  # la asociación se guarda en PostgreSQL

            print("\nContenedor asociado correctamente.")

            # Actualizar la asociación en Neo4j.
            sincronizar_envio_neo4j(id_envio)

        else:
            print(
                "No se pudo asociar. Puede que el contenedor "
                "ya esté asignado o no esté disponible."
            )

    except Exception as error:
        print(f"\nError al asociar contenedor: {mensaje_error(error)}")

    finally:
        pausar()


@requiere_permiso(1)
def consultar_contenedores_envio_service():  # lista los contenedores de un envío; opción 10 del menú de envíos
    print("\n--- CONTENEDORES DE UN ENVÍO ---")

    try:
        id_envio = pedir_id(
            "ID del envío: ",
            "El ID del envío"
        )

        envio = buscar_envio_por_id(id_envio)

        if envio is None:
            print("No existe un envío con ese ID.")
            return

        contenedores = listar_contenedores_de_envio(id_envio)

        if not contenedores:
            print("El envío no tiene contenedores asociados.")
            return

        print(f"\nEnvío: {id_envio}")
        print(f"Total de contenedores: {len(contenedores)}")

        for contenedor in contenedores:
            print("--------------------------------")
            print(f"ID: {contenedor[0]}")
            print(f"Código: {contenedor[1]}")
            print(f"Tipo: {contenedor[2]}")
            print(f"Capacidad: {formato.compacto(contenedor[3])} toneladas")
            print(f"Estado: {contenedor[4]}")

    except Exception as error:
        print(f"\nError al consultar contenedores: {mensaje_error(error)}")

    finally:
        pausar()


@requiere_permiso(1)
def desasociar_contenedor_service():  # saca un contenedor de un envío; opción 11 del menú de envíos
    print("\n--- DESASOCIAR CONTENEDOR ---")

    try:
        id_envio = pedir_id(
            "ID del envío: ",
            "El ID del envío"
        )

        envio = buscar_envio_por_id(id_envio)

        if envio is None:
            print("No existe un envío con ese ID.")
            return

        contenedores = listar_contenedores_de_envio(id_envio)

        if not contenedores:
            print("El envío no tiene contenedores asociados.")
            return

        print("\nContenedores asociados:")

        for contenedor in contenedores:
            print(
                f"ID: {contenedor[0]} | "
                f"Código: {contenedor[1]}"
            )

        id_contenedor = pedir_id(
            "\nID del contenedor a desasociar: ",
            "El ID del contenedor"
        )

        if not buscar_asociacion(id_envio, id_contenedor):
            print("Ese contenedor no está asociado al envío.")
            return

        confirmar = input(
            "¿Confirmar desasociación? (S/N): "
        ).strip().upper()

        if confirmar != "S":
            print("Operación cancelada.")
            return

        if desasociar_contenedor_db(id_envio, id_contenedor):  # borra la asociación en PostgreSQL

            print("\nContenedor desasociado correctamente.")

            # Actualizar Neo4j para quitar la asociación.
            sincronizar_envio_neo4j(id_envio)

        else:
            print("No se pudo desasociar.")

    except Exception as error:
        print(f"\nError al desasociar contenedor: {mensaje_error(error)}")

    finally:
        pausar()