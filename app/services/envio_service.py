from app.models.envio import Envio  # clase que arma el envío antes de guardarlo

from app.repositories.envio_repository import (  # consultas de envíos en PostgreSQL
    obtener_clientes,
    obtener_cliente_por_id,
    crear_envio,
    listar_envios,
    buscar_envio_por_id,
    actualizar_envio,
    actualizar_paises_envio,
    eliminar_envio_db
)

from app.utils.validaciones import (  # validaciones de lo que se tipea
    texto_obligatorio,
    validar_entero_positivo,
    validar_opcion
)

from app.services.sincronizacion_service import sincronizar_envio_neo4j  # copia el envío y sus tramos al grafo de Neo4j
from app.utils import formato
from app.utils.errores import mensaje_error  # traduce los errores a un mensaje claro, sin detalle técnico
from app.utils.validaciones_datos import validar_largo  # controla que el texto no supere el largo de la columna
from app.services.autenticacion import requiere_permiso  # cada pantalla verifica el permiso por su cuenta, además del menú


ESTADOS = [  # todos los estados que puede tener un envío
    "Pendiente",
    "En tránsito",
    "Entregado",
    "Cancelado"
]

# Entregado solo se alcanza registrando el evento ENTREGADO en Trazabilidad,
# que guarda la fecha real de entrega. No se elige a mano.
ESTADOS_EDITABLES = [  # los que se pueden elegir a mano (Entregado no)
    "Pendiente",
    "En tránsito",
    "Cancelado"
]

MENSAJE_ENTREGA = (  # aviso que se muestra al cambiar el estado
    "Para marcar un envío como Entregado registrá el evento ENTREGADO en "
    "Trazabilidad (guarda la fecha real de entrega)."
)


def es_entregado(estado):  # True si el estado es Entregado, sin importar mayúsculas; la usan modificar y eliminar envío
    return str(estado or "").strip().casefold() == "entregado"


PRIORIDADES = [  # prioridades válidas de un envío
    "Baja",
    "Media",
    "Alta"
]


def pedir_dato(mensaje, validador, *args):  # pide un dato hasta que pase la validación; la usan todas las pantallas de este archivo
    while True:
        try:
            return validador(input(mensaje), *args)  # valida lo que se escribió; si está mal, tira ValueError
        except ValueError as error:  # muestra el error y vuelve a pedir
            print(f"Error: {mensaje_error(error)}")


def pausar():
    input("\nPresioná Enter para continuar...")


def mostrar_envio(envio):  # imprime los datos de un envío; la usan registrar, listar, buscar, modificar y eliminar
    print("--------------------------------")
    print(f"ID envío: {envio[0]}")
    print(f"ID cliente: {envio[1]}")
    print(f"Cliente: {envio[2]}")
    pais_origen = envio[9] if len(envio) > 9 and envio[9] else "sin dato"  # los envíos viejos pueden no tener país
    pais_destino = envio[10] if len(envio) > 10 and envio[10] else "sin dato"
    print(f"Origen: {envio[3]} ({pais_origen})")
    print(f"Destino: {envio[4]} ({pais_destino})")
    print(f"Estado: {envio[5]}")
    print(f"Prioridad: {envio[6]}")
    print(f"Fecha de creación: {formato.fecha_hora(envio[7])}")
    if len(envio) > 8 and envio[8] is not None:  # la fecha de entrega solo existe si ya se entregó
        print(f"Fecha real de entrega: {formato.fecha_hora(envio[8])}")


def seleccionar_cliente():  # muestra los clientes y pide uno válido; la usan registrar envío y la opción 1 de modificar
    clientes = obtener_clientes()  # trae los clientes de PostgreSQL

    if not clientes:  # sin clientes no se puede crear un envío
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

    while True:  # pide un ID hasta que sea de un cliente que existe
        id_cliente = pedir_dato(
            "\nIngresá el ID del cliente: ",
            validar_entero_positivo,
            "El ID del cliente"
        )

        cliente = obtener_cliente_por_id(id_cliente)  # confirma en la base que el cliente existe

        if cliente is not None:
            return id_cliente

        print("No existe un cliente con ese ID.")


@requiere_permiso(1)  # nivel 1, igual que el menú de envíos
def registrar_envio():  # alta de un envío; opción 1 del menú de envíos
    print("\n--- REGISTRAR ENVÍO ---")

    try:
        id_cliente = seleccionar_cliente()  # primero se elige a qué cliente pertenece

        if id_cliente is None:  # no hay clientes: se corta acá
            return

        origen = pedir_dato(  # ciudad de origen, hasta 150 caracteres (el largo de la columna)
            "Origen: ",
            validar_largo,
            "El origen", 150
        )

        pais_origen = pedir_dato(  # país de origen, hasta 80 caracteres; la base lo exige en envíos nuevos
            "País de origen: ",
            validar_largo,
            "El país de origen", 80
        )

        destino = pedir_dato(  # ciudad de destino, hasta 150 caracteres
            "Destino: ",
            validar_largo,
            "El destino", 150
        )

        pais_destino = pedir_dato(  # país de destino, hasta 80 caracteres
            "País de destino: ",
            validar_largo,
            "El país de destino", 80
        )

        estado = pedir_dato(  # solo Pendiente, En tránsito o Cancelado
            "Estado (Pendiente/En tránsito/Cancelado): ",
            validar_opcion,
            ESTADOS_EDITABLES,
            "El estado"
        )

        prioridad = pedir_dato(  # Baja, Media o Alta
            "Prioridad (Baja/Media/Alta): ",
            validar_opcion,
            PRIORIDADES,
            "La prioridad"
        )

        envio = Envio(  # arma el objeto con los datos ya validados
            id_cliente,
            origen,
            destino,
            estado,
            prioridad,
            pais_origen=pais_origen,
            pais_destino=pais_destino
        )

        id_envio = crear_envio(envio)  # lo guarda en PostgreSQL y devuelve el ID

        # Sincronizar el nuevo envío con Neo4j.
        sincronizar_envio_neo4j(id_envio)  # si Neo4j falla queda pendiente, pero el envío ya está guardado

        print("\nEnvío registrado correctamente.")
        print(f"ID del envío generado: {id_envio}")

        envio_guardado = buscar_envio_por_id(id_envio)  # lo vuelve a leer para mostrar cómo quedó

        if envio_guardado:
            mostrar_envio(envio_guardado)

    except Exception as error:  # cualquier error se muestra traducido
        print(f"\nError al registrar el envío: {mensaje_error(error)}")

    finally:
        pausar()


@requiere_permiso(1)  # nivel 1, igual que el menú de envíos
def listar_envios_service():  # lista todos los envíos; opción 2 del menú de envíos
    print("\n--- LISTAR ENVÍOS ---")

    try:
        envios = listar_envios()  # consulta en PostgreSQL

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


@requiere_permiso(1)  # nivel 1, igual que el menú de envíos
def buscar_envio_service():  # busca un envío por ID; opción 3 del menú de envíos
    print("\n--- BUSCAR ENVÍO ---")

    try:
        id_envio = pedir_dato(
            "Ingresá el ID del envío: ",
            validar_entero_positivo,
            "El ID del envío"
        )

        envio = buscar_envio_por_id(id_envio)  # None si no existe

        if envio is None:
            print("\nNo se encontró un envío con ese ID.")
            return

        mostrar_envio(envio)

    except Exception as error:
        print(f"\nError al buscar el envío: {mensaje_error(error)}")

    finally:
        pausar()


@requiere_permiso(1)  # nivel 1, igual que el menú de envíos
def modificar_envio_service():  # cambia un dato del envío; opción 4 del menú de envíos
    print("\n--- MODIFICAR ENVÍO ---")

    try:
        id_envio = pedir_dato(
            "Ingresá el ID del envío a modificar: ",
            validar_entero_positivo,
            "El ID del envío"
        )

        envio_actual = buscar_envio_por_id(id_envio)  # datos actuales: se comparan con los nuevos y se conservan los que no cambian

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

        if opcion not in ["1", "2", "3", "4", "5", "6"]:  # cualquier otra cosa es inválida
            print("Opción inválida.")
            return

        # Países: se pueden completar o corregir en cualquier estado
        # (los envíos anteriores a la migración 014 no los tienen).
        if opcion == "6":  # los países se cambian aparte, en cualquier estado
            pais_origen = pedir_dato(
                "País de origen: ", validar_largo, "El país de origen", 80
            )
            pais_destino = pedir_dato(
                "País de destino: ", validar_largo, "El país de destino", 80
            )
            if actualizar_paises_envio(id_envio, pais_origen, pais_destino):  # actualiza solo los dos países
                print("\nPaíses actualizados.")
                mostrar_envio(buscar_envio_por_id(id_envio))
            else:
                print("\nNo se pudieron actualizar los países.")
            return

        # Entregado es final: solo se puede cambiar la prioridad (los
        # países se resolvieron antes).
        if es_entregado(envio_actual[5]) and opcion not in ("5", "6"):  # un envío entregado solo admite cambiar la prioridad
            print(
                "\nEl envío está Entregado: su cliente, ruta y estado ya no "
                "se modifican."
            )
            return

        id_cliente = envio_actual[1]  # arranca con los valores actuales; abajo se reemplaza solo el que se eligió
        origen = envio_actual[3]
        destino = envio_actual[4]
        estado = envio_actual[5]
        prioridad = envio_actual[6]

        if opcion == "1":  # cambiar de cliente
            nuevo_cliente = seleccionar_cliente()

            if nuevo_cliente is None:
                return

            id_cliente = nuevo_cliente

        elif opcion == "2":  # cambiar el origen
            origen = pedir_dato(
                "Nuevo origen: ",
                validar_largo,
                "El origen", 150
            )

        elif opcion == "3":  # cambiar el destino
            destino = pedir_dato(
                "Nuevo destino: ",
                validar_largo,
                "El destino", 150
            )

        elif opcion == "4":  # cambiar el estado (Entregado no se elige acá)
            print(MENSAJE_ENTREGA)
            estado = pedir_dato(
                "Nuevo estado (Pendiente/En tránsito/Cancelado): ",
                validar_opcion,
                ESTADOS_EDITABLES,
                "El estado"
            )

        elif opcion == "5":  # cambiar la prioridad
            prioridad = pedir_dato(
                "Nueva prioridad (Baja/Media/Alta): ",
                validar_opcion,
                PRIORIDADES,
                "La prioridad"
            )

        # No alterar extremos de una ruta que ya tiene tramos registrados.
        if opcion in ("2", "3") and (  # si se tocó la ruta
            origen != envio_actual[3] or destino != envio_actual[4]  # y quedó distinta de la que había
        ):
            from app.repositories.tramo_repository import listar_tramos_de_envio  # se importa acá porque solo hace falta en este caso

            if listar_tramos_de_envio(id_envio):  # con tramos cargados no se puede mover el origen ni el destino
                print(
                    "\nNo se puede cambiar el origen o destino: "
                    "el envío ya tiene tramos registrados."
                )
                return

        envio_modificado = Envio(  # el mismo envío con el dato nuevo
            id_cliente,
            origen,
            destino,
            estado,
            prioridad
        )

        actualizado = actualizar_envio(  # el UPDATE vuelve a controlar en la base que la ruta no cambie si hay tramos
            id_envio,
            envio_modificado
        )

        if actualizado:  # solo si la base actualizó alguna fila
            # Sincronizar los cambios del envío con Neo4j.
            sincronizar_envio_neo4j(id_envio)  # actualiza el envío en el grafo

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


@requiere_permiso(1)  # nivel 1, igual que el menú de envíos
def eliminar_envio_service():  # borra un envío; opción 5 del menú de envíos
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

        if es_entregado(envio[5]):  # los entregados no se borran porque ya se facturaron
            print(
                "\nUn envío Entregado no se elimina: es la base de su "
                "facturación y de la de sus operadores."
            )
            return

        confirmacion = input(
            "\n¿Seguro que querés eliminar este envío? (S/N): "
        ).strip().upper()

        if confirmacion != "S":  # cualquier respuesta que no sea S cancela
            print("Eliminación cancelada.")
            return

        eliminado = eliminar_envio_db(id_envio)  # DELETE en PostgreSQL

        if eliminado:
            # El envío ya no existe en PostgreSQL.
            # La sincronización elimina su proyección de Neo4j.
            sincronizar_envio_neo4j(id_envio)  # como ya no está en PostgreSQL, lo saca del grafo

            print("\nEnvío eliminado correctamente.")
        else:
            print("\nNo se pudo eliminar el envío.")

    except Exception as error:  # por ejemplo, si tiene tramos o contenedores la base no deja borrarlo
        print(f"\nError al eliminar el envío: {mensaje_error(error)}")
        print(
            "Si el envío tiene tramos, incidentes o contenedores "
            "asociados, el sistema puede impedir su eliminación."
        )

    finally:
        pausar()