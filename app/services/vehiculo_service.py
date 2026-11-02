from app.models.vehiculo import Vehiculo

from app.repositories.vehiculo_repository import (
    crear_vehiculo,
    listar_vehiculos,
    buscar_vehiculo_por_id,
    buscar_vehiculo_por_identificacion,
    actualizar_vehiculo,
    eliminar_vehiculo_db,
    contar_tramos_de_vehiculo
)
from app.repositories.terceros_repository import (
    listar_operadores_por_modalidad
)

from app.utils.validaciones_logistica import (
    TIPOS_VEHICULO,
    ESTADOS_VEHICULO,
    validar_opcion_flexible,
    validar_texto,
    validar_identificacion,
    validar_entero_positivo_logistica
)
from app.utils.errores import mensaje_error
from app.services.autenticacion import requiere_permiso


def pedir(mensaje, funcion, *args):
    while True:
        try:
            return funcion(input(mensaje), *args)
        except ValueError as error:
            print(f"Error: {mensaje_error(error)}")


def pausar():
    input("\nPresioná Enter para continuar...")


def mostrar_vehiculo(vehiculo):
    print("--------------------------------")
    print(f"ID vehículo: {vehiculo[0]}")
    print(f"Tipo: {vehiculo[1]}")
    print(f"Identificación: {vehiculo[2]}")
    if vehiculo[5] is not None:
        print(f"Operador logístico: {vehiculo[6]} (ID {vehiculo[5]})")
    else:
        print("Operador logístico: sin asignar")
    if vehiculo[3]:
        print(f"Empresa operadora (texto histórico): {vehiculo[3]}")
    print(f"Estado: {vehiculo[4]}")


def mostrar_ayuda_identificacion(tipo):
    print("\n--- IDENTIFICACIÓN DEL VEHÍCULO ---")

    if tipo == "Terrestre":
        print("Ingresá la patente del vehículo.")
        print("Ejemplo: AB123CD")

    elif tipo == "Marítimo":
        print("Ingresá el identificador del buque.")
        print("Ejemplo: IMO 9876543")

    elif tipo == "Aéreo":
        print("Ingresá la matrícula de la aeronave.")
        print("Ejemplo: LV-ABC")


def pedir_identificacion(id_vehiculo_actual=None):
    while True:
        identificacion = pedir(
            "Identificación del vehículo: ",
            validar_identificacion
        )

        existente = buscar_vehiculo_por_identificacion(
            identificacion
        )

        if existente is None:
            return identificacion

        if (
            id_vehiculo_actual is not None
            and existente[0] == id_vehiculo_actual
        ):
            return identificacion

        print(
            "Error: ya existe un vehículo con esa identificación."
        )


def pedir_operador(tipo):
    """Elige un operador activo con la modalidad del vehículo (o ninguno)."""
    operadores = listar_operadores_por_modalidad(tipo)

    if not operadores:
        print(
            f"\nNo hay operadores logísticos activos con modalidad {tipo}. "
            "El vehículo queda sin operador (se puede asignar después)."
        )
        return None

    print(f"\nOperadores logísticos con modalidad {tipo}:")
    for operador in operadores:
        print(f"  {operador[0]}. {operador[1]}")

    ids = {operador[0] for operador in operadores}

    while True:
        valor = input(
            "ID del operador (Enter si no corresponde): "
        ).strip()

        if not valor:
            return None

        if valor.isdigit() and int(valor) in ids:
            return int(valor)

        print("Error: elegí uno de los operadores listados.")


@requiere_permiso(1)
def registrar_vehiculo():
    print("\n--- REGISTRAR VEHÍCULO ---")

    try:
        tipo = pedir(
            "Tipo (Terrestre/Marítimo/Aéreo): ",
            validar_opcion_flexible,
            TIPOS_VEHICULO,
            "El tipo"
        )

        mostrar_ayuda_identificacion(tipo)

        identificacion = pedir_identificacion()

        id_operador = pedir_operador(tipo)

        estado = pedir(
            "Estado (Disponible/En uso/Mantenimiento/Inactivo): ",
            validar_opcion_flexible,
            ESTADOS_VEHICULO,
            "El estado"
        )

        vehiculo = Vehiculo(
            tipo,
            identificacion,
            None,
            estado,
            id_operador
        )

        id_vehiculo = crear_vehiculo(vehiculo)

        print("\nVehículo registrado correctamente.")
        print(f"ID generado: {id_vehiculo}")

        vehiculo_guardado = buscar_vehiculo_por_id(
            id_vehiculo
        )

        mostrar_vehiculo(vehiculo_guardado)

    except Exception as error:
        print(f"\nError al registrar el vehículo: {mensaje_error(error)}")

    finally:
        pausar()


@requiere_permiso(1)
def listar_vehiculos_service():
    print("\n--- LISTAR VEHÍCULOS ---")

    try:
        vehiculos = listar_vehiculos()

        if not vehiculos:
            print("No hay vehículos registrados.")
            return

        print(f"\nTotal de vehículos: {len(vehiculos)}")

        for vehiculo in vehiculos:
            mostrar_vehiculo(vehiculo)

    except Exception as error:
        print(f"\nError al listar vehículos: {mensaje_error(error)}")

    finally:
        pausar()


@requiere_permiso(1)
def buscar_vehiculo_service():
    print("\n--- BUSCAR VEHÍCULO ---")

    try:
        id_vehiculo = pedir(
            "ID del vehículo: ",
            validar_entero_positivo_logistica,
            "El ID del vehículo"
        )

        vehiculo = buscar_vehiculo_por_id(id_vehiculo)

        if vehiculo is None:
            print("\nNo existe un vehículo con ese ID.")
            return

        mostrar_vehiculo(vehiculo)

    except Exception as error:
        print(f"\nError al buscar vehículo: {mensaje_error(error)}")

    finally:
        pausar()


@requiere_permiso(1)
def modificar_vehiculo_service():
    print("\n--- MODIFICAR VEHÍCULO ---")

    try:
        id_vehiculo = pedir(
            "ID del vehículo: ",
            validar_entero_positivo_logistica,
            "El ID del vehículo"
        )

        actual = buscar_vehiculo_por_id(id_vehiculo)

        if actual is None:
            print("\nNo existe un vehículo con ese ID.")
            return

        print("\nDatos actuales:")
        mostrar_vehiculo(actual)

        print("\n¿Qué querés modificar?")
        print("1. Tipo de vehículo")
        print("2. Identificación")
        print("3. Operador logístico")
        print("4. Estado")
        print("0. Cancelar")

        opcion = input("\nSeleccioná una opción: ").strip()

        if opcion == "0":
            print("Modificación cancelada.")
            return

        if opcion not in ["1", "2", "3", "4"]:
            print("Opción inválida.")
            return

        tipo = actual[1]
        identificacion = actual[2]
        estado = actual[4]
        id_operador = actual[5]

        if opcion == "1":
            if contar_tramos_de_vehiculo(id_vehiculo) > 0:
                print(
                    "\nNo se puede cambiar el tipo de un vehículo "
                    "que tiene tramos asociados."
                )
                return

            tipo = pedir(
                "Nuevo tipo (Terrestre/Marítimo/Aéreo): ",
                validar_opcion_flexible,
                TIPOS_VEHICULO,
                "El tipo"
            )

            mostrar_ayuda_identificacion(tipo)

            # Si cambia el tipo, solicitamos una identificación
            # correspondiente al nuevo tipo de vehículo.
            if tipo != actual[1]:
                identificacion = pedir_identificacion(
                    id_vehiculo
                )

                # El operador anterior puede no tener la nueva modalidad.
                if id_operador is not None:
                    print(
                        "\nCambió el tipo: elegí de nuevo el operador."
                    )
                    id_operador = pedir_operador(tipo)

        elif opcion == "2":
            mostrar_ayuda_identificacion(tipo)

            identificacion = pedir_identificacion(
                id_vehiculo
            )

        elif opcion == "3":
            id_operador = pedir_operador(tipo)

        elif opcion == "4":
            estado = pedir(
                "Nuevo estado (Disponible/En uso/Mantenimiento/Inactivo): ",
                validar_opcion_flexible,
                ESTADOS_VEHICULO,
                "El estado"
            )

        vehiculo_modificado = Vehiculo(
            tipo,
            identificacion,
            actual[3],
            estado,
            id_operador
        )

        actualizado = actualizar_vehiculo(
            id_vehiculo,
            vehiculo_modificado
        )

        if actualizado:
            print("\nVehículo modificado correctamente.")

            mostrar_vehiculo(
                buscar_vehiculo_por_id(id_vehiculo)
            )
        else:
            print("\nNo se pudo modificar el vehículo.")

    except Exception as error:
        print(f"\nError al modificar vehículo: {mensaje_error(error)}")

    finally:
        pausar()


@requiere_permiso(1)
def eliminar_vehiculo_service():
    print("\n--- ELIMINAR VEHÍCULO ---")

    try:
        id_vehiculo = pedir(
            "ID del vehículo: ",
            validar_entero_positivo_logistica,
            "El ID del vehículo"
        )

        vehiculo = buscar_vehiculo_por_id(id_vehiculo)

        if vehiculo is None:
            print("\nNo existe un vehículo con ese ID.")
            return

        if contar_tramos_de_vehiculo(id_vehiculo) > 0:
            print(
                "\nNo se puede eliminar el vehículo porque "
                "tiene tramos asociados."
            )
            return

        print("\nVehículo seleccionado:")
        mostrar_vehiculo(vehiculo)

        confirmacion = input(
            "\n¿Seguro que querés eliminar este vehículo? (S/N): "
        ).strip().upper()

        if confirmacion != "S":
            print("\nEliminación cancelada.")
            return

        eliminado = eliminar_vehiculo_db(id_vehiculo)

        if eliminado:
            print("\nVehículo eliminado correctamente.")
        else:
            print("\nNo se pudo eliminar el vehículo.")

    except Exception as error:
        print(f"\nError al eliminar vehículo: {mensaje_error(error)}")

    finally:
        pausar()