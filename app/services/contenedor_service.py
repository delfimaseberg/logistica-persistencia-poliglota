from app.models.contenedor import Contenedor

from app.repositories.contenedor_repository import (
    crear_contenedor,
    listar_contenedores,
    buscar_contenedor_por_id,
    buscar_contenedor_por_codigo,
    actualizar_contenedor,
    eliminar_contenedor_db,
    contar_asociaciones_contenedor,
    contar_sensores_contenedor
)

from app.utils.validaciones_contenedor import (
    validar_codigo_internacional,
    validar_tipo_contenedor,
    validar_estado_contenedor,
    validar_capacidad
)

from app.utils.validaciones_logistica import (
    validar_entero_positivo_logistica
)
from app.utils.errores import mensaje_error
from app.utils import formato
from app.services.autenticacion import requiere_permiso


def pedir(mensaje, funcion):  # repite la pregunta hasta que la validación pase; la usan todas las pantallas de acá
    while True:
        try:
            return funcion(input(mensaje))
        except ValueError as error:
            print(f"Error: {mensaje_error(error)}")


def pausar():
    input("\nPresioná Enter para continuar...")


def mostrar_contenedor(contenedor):  # imprime los datos de un contenedor; la usan alta, listado, búsqueda y modificación
    print("--------------------------------")
    print(f"ID contenedor: {contenedor[0]}")
    print(f"Código internacional: {contenedor[1]}")
    print(f"Tipo: {contenedor[2]}")
    print(f"Capacidad: {formato.compacto(contenedor[3])} toneladas")
    print(f"Estado: {contenedor[4]}")


def pedir_codigo(id_actual=None):  # pide un código válido que no esté repetido; la usan alta y modificación
    while True:
        codigo = pedir(
            "Código internacional (3 letras + U + 6 números + dígito de control, ej. MSCU1234566): ",
            validar_codigo_internacional
        )

        existente = buscar_contenedor_por_codigo(codigo)  # el código internacional no se puede repetir

        if existente is None or existente[0] == id_actual:
            return codigo

        print("Error: ese código ya está registrado.")


@requiere_permiso(1)
def registrar_contenedor():  # da de alta un contenedor; opción 1 del menú de contenedores
    print("\n--- REGISTRAR CONTENEDOR ---")

    try:
        codigo = pedir_codigo()

        tipo = pedir(
            "Tipo (Seco/Refrigerado/Tanque/Open Top): ",
            validar_tipo_contenedor
        )

        capacidad = pedir(
            "Capacidad en toneladas: ",
            validar_capacidad
        )

        estado = pedir(
            "Estado (Disponible/En uso/Mantenimiento/Inactivo): ",
            validar_estado_contenedor
        )

        contenedor = Contenedor(
            codigo,
            tipo,
            capacidad,
            estado
        )

        id_contenedor = crear_contenedor(contenedor)  # INSERT en PostgreSQL

        print("\nContenedor registrado correctamente.")
        print(f"ID generado: {id_contenedor}")

        mostrar_contenedor(
            buscar_contenedor_por_id(id_contenedor)
        )

    except Exception as error:
        print(f"\nError al registrar el contenedor: {mensaje_error(error)}")

    finally:
        pausar()


@requiere_permiso(1)
def listar_contenedores_service():  # lista todos los contenedores; opción 2 del menú de contenedores
    print("\n--- LISTAR CONTENEDORES ---")

    try:
        contenedores = listar_contenedores()

        if not contenedores:
            print("No hay contenedores registrados.")
            return

        print(f"\nTotal: {len(contenedores)}")

        for contenedor in contenedores:
            mostrar_contenedor(contenedor)

    except Exception as error:
        print(f"\nError al listar contenedores: {mensaje_error(error)}")

    finally:
        pausar()


@requiere_permiso(1)
def buscar_contenedor_service():  # muestra un contenedor por su ID; opción 3 del menú de contenedores
    print("\n--- BUSCAR CONTENEDOR ---")

    try:
        id_contenedor = pedir(
            "ID del contenedor: ",
            lambda valor: validar_entero_positivo_logistica(
                valor, "El ID del contenedor"
            )
        )

        contenedor = buscar_contenedor_por_id(id_contenedor)

        if contenedor is None:
            print("No existe un contenedor con ese ID.")
            return

        mostrar_contenedor(contenedor)

    except Exception as error:
        print(f"\nError al buscar contenedor: {mensaje_error(error)}")

    finally:
        pausar()


@requiere_permiso(1)
def modificar_contenedor_service():  # cambia un dato del contenedor; opción 4 del menú de contenedores
    print("\n--- MODIFICAR CONTENEDOR ---")

    try:
        id_contenedor = pedir(
            "ID del contenedor: ",
            lambda valor: validar_entero_positivo_logistica(
                valor, "El ID del contenedor"
            )
        )

        actual = buscar_contenedor_por_id(id_contenedor)

        if actual is None:
            print("No existe un contenedor con ese ID.")
            return

        mostrar_contenedor(actual)

        print("\n¿Qué querés modificar?")
        print("1. Código internacional")
        print("2. Tipo")
        print("3. Capacidad")
        print("4. Estado")
        print("0. Cancelar")

        opcion = input("Opción: ").strip()

        if opcion == "0":
            return

        if opcion not in ("1", "2", "3", "4"):
            print("Opción inválida.")
            return

        codigo = actual[1]  # arranca con los datos actuales y solo cambia el elegido
        tipo = actual[2]
        capacidad = actual[3]
        estado = actual[4]

        if opcion == "1":
            codigo = pedir_codigo(id_contenedor)

        elif opcion == "2":
            tipo = pedir(
                "Nuevo tipo: ",
                validar_tipo_contenedor
            )

        elif opcion == "3":
            capacidad = pedir(
                "Nueva capacidad en toneladas: ",
                validar_capacidad
            )

        elif opcion == "4":
            nuevo_estado = pedir(
                "Nuevo estado: ",
                validar_estado_contenedor
            )

            if (  # si está asociado a un envío, solo puede quedar Disponible o En uso
                contar_asociaciones_contenedor(id_contenedor) > 0
                and nuevo_estado != "Disponible"
                and nuevo_estado != "En uso"
            ):
                print(
                    "No se puede poner en mantenimiento o inactivo "
                    "un contenedor asociado a un envío."
                )
                return

            estado = nuevo_estado

        contenedor = Contenedor(
            codigo,
            tipo,
            capacidad,
            estado
        )

        if actualizar_contenedor(id_contenedor, contenedor):  # UPDATE en PostgreSQL
            print("\nContenedor modificado correctamente.")
            mostrar_contenedor(
                buscar_contenedor_por_id(id_contenedor)
            )
        else:
            print("No se pudo modificar el contenedor.")

    except Exception as error:
        print(f"\nError al modificar contenedor: {mensaje_error(error)}")

    finally:
        pausar()


@requiere_permiso(1)
def eliminar_contenedor_service():  # borra un contenedor sin envíos ni sensores; opción 5 del menú de contenedores
    print("\n--- ELIMINAR CONTENEDOR ---")

    try:
        id_contenedor = pedir(
            "ID del contenedor: ",
            lambda valor: validar_entero_positivo_logistica(
                valor, "El ID del contenedor"
            )
        )

        contenedor = buscar_contenedor_por_id(id_contenedor)

        if contenedor is None:
            print("No existe un contenedor con ese ID.")
            return

        if contar_asociaciones_contenedor(id_contenedor) > 0:  # no se borra si está en un envío
            print(
                "No se puede eliminar porque está asociado "
                "a un envío."
            )
            return

        if contar_sensores_contenedor(id_contenedor) > 0:  # ni si tiene sensores
            print(
                "No se puede eliminar porque tiene "
                "sensores IoT asociados."
            )
            return

        mostrar_contenedor(contenedor)

        confirmacion = input(
            "\n¿Confirmás la eliminación? (S/N): "
        ).strip().upper()

        if confirmacion != "S":
            print("Eliminación cancelada.")
            return

        if eliminar_contenedor_db(id_contenedor):
            print("Contenedor eliminado correctamente.")
        else:
            print("No se pudo eliminar.")

    except Exception as error:
        print(f"\nError al eliminar contenedor: {mensaje_error(error)}")

    finally:
        pausar()