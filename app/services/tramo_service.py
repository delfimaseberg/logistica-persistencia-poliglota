from app.models.tramo import Tramo  # clase que arma el tramo antes de guardarlo

from app.repositories.envio_repository import buscar_envio_por_id  # para traer el envío al que se le agrega el tramo
from app.repositories.vehiculo_repository import (  # vehículos para elegir el que hace el tramo
    listar_vehiculos,
    buscar_vehiculo_por_id
)
from app.repositories.tramo_repository import (  # alta y consulta de tramos en PostgreSQL
    crear_tramo,
    listar_tramos_de_envio
)
from app.repositories.terceros_repository import (  # operadores logísticos según la modalidad
    listar_operadores_por_modalidad
)

from app.utils.validaciones_logistica import (  # validaciones de textos, fechas e IDs de esta parte
    validar_texto,
    validar_fecha,
    validar_rango_fechas,
    sale_despues_de_llegar,  # compara las fechas en hora argentina para encadenar tramos
    validar_entero_positivo_logistica,
    normalizar  # pasa a minúsculas y sin tildes para comparar textos
)

from app.services.sincronizacion_service import sincronizar_envio_neo4j  # copia el tramo al grafo de Neo4j
from app.utils import formato
from app.utils.errores import mensaje_error
from app.services.autenticacion import requiere_permiso  # cada pantalla verifica el permiso por su cuenta, además del menú


def pedir(mensaje, funcion, *args):  # pide un dato hasta que la validación lo acepte; la usan registrar y consultar tramos
    while True:
        try:
            return funcion(input(mensaje), *args)  # valida lo tipeado; si está mal, tira ValueError
        except ValueError as error:
            print(f"Error: {mensaje_error(error)}")


def pausar():
    input("\nPresioná Enter para continuar...")


def pedir_ubicacion(mensaje, valor_sugerido=None):  # pide una ciudad ofreciendo una sugerencia; registrar_tramo la usa para el destino
    while True:
        if valor_sugerido:  # muestra la sugerencia entre corchetes
            valor = input(
                f"{mensaje} [{valor_sugerido}]: "
            ).strip()

            if not valor:  # con Enter se acepta la sugerencia
                valor = valor_sugerido
        else:
            valor = input(f"{mensaje}: ").strip()

        try:
            return validar_texto(valor, mensaje, 150)  # obligatoria y hasta 150 caracteres
        except ValueError as error:
            print(f"Error: {mensaje_error(error)}")


def elegir_operador_tramo(vehiculo, medio):  # decide qué operador hace el tramo; la usa registrar_tramo
    """Devuelve (id_operador, razón social) o None si no hay ninguno válido.

    Usa el operador del vehículo cuando está activo y tiene la modalidad;
    si no, pide elegir entre los operadores activos de esa modalidad.
    """
    operadores = listar_operadores_por_modalidad(medio)  # operadores activos que trabajan con ese medio (Terrestre, Marítimo o Aéreo)
    por_id = {operador[0]: operador[1] for operador in operadores}  # id -> razón social, para buscar rápido

    id_del_vehiculo = vehiculo[5] if len(vehiculo) > 5 else None  # operador asignado al vehículo, si tiene
    if id_del_vehiculo in por_id:  # si sirve para ese medio, se usa directamente
        return id_del_vehiculo, por_id[id_del_vehiculo]

    if id_del_vehiculo is not None:  # tiene operador pero no sirve: se avisa
        print(
            "\nEl operador del vehículo está inactivo o no tiene la "
            f"modalidad {medio}. Elegí otro."
        )

    if not operadores:  # no hay ninguno con esa modalidad: no se puede registrar el tramo
        return None

    print(f"\nOperadores logísticos con modalidad {medio}:")
    for operador in operadores:
        print(f"  {operador[0]}. {operador[1]}")

    while True:  # pide un ID hasta que sea uno de los listados
        valor = input("ID del operador que realiza el tramo: ").strip()
        if valor.isdigit() and int(valor) in por_id:  # solo acepta operadores de la lista
            return int(valor), por_id[int(valor)]
        print("Error: elegí uno de los operadores listados.")


@requiere_permiso(1)  # nivel 1, igual que el menú de envíos
def registrar_tramo():  # agrega un tramo al recorrido de un envío; opción 7 del menú de envíos
    print("\n--- REGISTRAR TRAMO ---")

    try:
        id_envio = pedir(
            "ID del envío: ",
            validar_entero_positivo_logistica,
            "El ID del envío"
        )

        envio = buscar_envio_por_id(id_envio)  # trae el envío de PostgreSQL

        if envio is None:
            print("No existe un envío con ese ID.")
            return

        if normalizar(envio[5]) in ("cancelado", "entregado"):  # a un envío cerrado no se le agregan tramos
            print(
                "No se pueden agregar tramos a un envío "
                "cancelado o entregado."
            )
            return

        tramos_existentes = listar_tramos_de_envio(id_envio)  # tramos ya cargados, en orden de salida

        print("\n--- DATOS DEL ENVÍO ---")
        print(f"Cliente: {envio[2]}")
        print(f"Origen general: {envio[3]}")
        print(f"Destino final: {envio[4]}")

        if tramos_existentes:  # si ya hay tramos, el nuevo sale de donde terminó el último
            print("\nTramos registrados:")

            for numero, tramo in enumerate(
                tramos_existentes, start=1
            ):
                print(
                    f"{numero}. {tramo[5]} → {tramo[6]} "
                    f"({tramo[4]})"
                )

            ultimo_tramo = tramos_existentes[-1]  # el último del recorrido
            origen_sugerido = ultimo_tramo[6]  # su destino es el origen del tramo nuevo

            print(
                "\nSe sugiere continuar desde el destino "
                "del último tramo registrado."
            )

        else:  # primer tramo: sale del origen del envío
            origen_sugerido = envio[3]

            print(
                "\nEste es el primer tramo del envío. "
                "Se sugiere comenzar desde su origen."
            )

        vehiculos = listar_vehiculos()  # todos los vehículos de PostgreSQL

        disponibles = [  # solo los que están Disponibles
            v for v in vehiculos
            if normalizar(v[4]) == "disponible"
        ]

        if not disponibles:  # sin vehículos libres no se puede seguir
            print(
                "\nNo hay vehículos disponibles. "
                "Primero registrá uno."
            )
            return

        print("\n--- VEHÍCULOS DISPONIBLES ---")

        for vehiculo in disponibles:
            print(
                f"ID: {vehiculo[0]} | "
                f"Tipo: {vehiculo[1]} | "
                f"Identificación: {vehiculo[2]}"
            )

        while True:  # pide un vehículo hasta que sea válido
            id_vehiculo = pedir(
                "\nID del vehículo: ",
                validar_entero_positivo_logistica,
                "El ID del vehículo"
            )

            vehiculo = buscar_vehiculo_por_id(id_vehiculo)  # confirma que existe

            if vehiculo is None:
                print("El vehículo no existe.")
                continue

            if normalizar(vehiculo[4]) != "disponible":  # no se puede usar uno en uso o en mantenimiento
                print("El vehículo no está disponible.")
                continue

            break

        # El medio se obtiene automáticamente del vehículo.
        medio = vehiculo[1]  # Terrestre, Marítimo o Aéreo, según el tipo del vehículo

        print("\nVehículo seleccionado:")
        print(f"Identificación: {vehiculo[2]}")
        print(f"Medio de transporte: {medio} (automático)")

        # El operador del tramo es obligatorio: se toma del vehículo si lo
        # tiene (activo y con la modalidad); si no, se elige uno.
        operador = elegir_operador_tramo(vehiculo, medio)  # el del vehículo o uno elegido de la lista

        if operador is None:  # sin operador válido no se registra el tramo
            print(
                f"\nNo se puede registrar el tramo sin operador. Registrá "
                f"un operador logístico activo con modalidad {medio}."
            )
            return

        id_operador, nombre_operador = operador
        print(f"Operador logístico: {nombre_operador}")

        # El origen continúa el recorrido registrado.
        origen = origen_sugerido  # no se pregunta: sigue el recorrido

        print(f"\nOrigen del tramo: {origen} (automático)")

        destino = pedir_ubicacion(  # se sugiere el destino final del envío
            "Destino del tramo",
            envio[4]
        )

        if normalizar(origen) == normalizar(destino):  # compara sin tildes ni mayúsculas
            print(
                "\nError: el origen y destino del tramo "
                "no pueden ser iguales."
            )
            return

        # No permitir nuevos tramos si ya se llegó al destino final.
        if tramos_existentes:  # solo tiene sentido si ya hay tramos
            if normalizar(ultimo_tramo[6]) == normalizar(envio[4]):  # el último tramo ya llega al destino final
                print(
                    "\nEl recorrido ya llegó al destino final. "
                    "No se pueden agregar más tramos."
                )
                return

        while True:  # pide las fechas hasta que sean coherentes
            fecha_salida = pedir(  # el día de salida, a las 00:00 hora argentina
                "Fecha de salida (AAAA-MM-DD): ",
                validar_fecha,
                "La fecha de salida"
            )

            fecha_llegada = pedir(  # el día estimado de llegada, hasta las 23:59:59
                "Fecha estimada de llegada (AAAA-MM-DD): ",
                validar_fecha,
                "La fecha estimada de llegada",
                True                      # vale hasta las 23:59:59 de ese día
            )

            try:
                validar_rango_fechas(  # la llegada no puede ser anterior a la salida
                    fecha_salida,
                    fecha_llegada
                )

                if tramos_existentes:  # si hay un tramo anterior, el nuevo se encadena con él
                    ultima_llegada = ultimo_tramo[8]  # llegada estimada del tramo anterior

                    if not sale_despues_de_llegar(fecha_salida, ultima_llegada):  # puede salir el mismo día en que llegó el anterior, pero no antes
                        print(
                            "Error: el nuevo tramo no puede "
                            "salir antes de la llegada estimada "
                            "del tramo anterior."
                        )
                        continue

                break

            except ValueError as error:  # fechas incoherentes: se muestra el error y se vuelven a pedir
                print(f"Error: {mensaje_error(error)}")

        tramo = Tramo(  # arma el tramo con todos los datos ya validados
            id_envio,
            id_vehiculo,
            medio,
            origen,
            destino,
            fecha_salida,
            fecha_llegada,
            id_operador
        )

        print("\n--- RESUMEN DEL TRAMO ---")
        print(f"Envío: {id_envio}")
        print(f"Vehículo: {vehiculo[2]}")
        print(f"Operador: {nombre_operador}")
        print(f"Medio: {medio}")
        print(f"Origen: {origen}")
        print(f"Destino: {destino}")
        print(f"Salida: {formato.fecha_tramo(fecha_salida)}")  # solo la fecha, porque se cargó sin hora
        print(f"Llegada estimada: {formato.fecha_tramo(fecha_llegada)}")

        confirmacion = input(
            "\n¿Confirmar registro? (S/N): "
        ).strip().upper()

        if confirmacion != "S":  # sin confirmar no se guarda nada
            print("Registro cancelado.")
            return

        id_tramo = crear_tramo(tramo)  # INSERT en PostgreSQL

        print("\nTramo registrado correctamente.")
        print(f"ID generado: {id_tramo}")

        # Sincronizar el nuevo tramo con Neo4j.
        # Se ejecuta después de guardar correctamente en PostgreSQL.
        sincronizar_envio_neo4j(id_envio)  # si Neo4j no responde, queda pendiente para reintentar

        if normalizar(destino) == normalizar(envio[4]):  # avisa si con este tramo se completa el recorrido
            print(
                "Este tramo llega al destino final del envío."
            )

    except Exception as error:  # errores de base o de conexión, traducidos
        print(f"\nError al registrar el tramo: {mensaje_error(error)}")

    finally:
        pausar()


@requiere_permiso(1)  # nivel 1, igual que el menú de envíos
def consultar_tramos_service():  # muestra los tramos de un envío; opción 8 del menú de envíos
    print("\n--- CONSULTAR TRAMOS DE UN ENVÍO ---")

    try:
        id_envio = pedir(
            "ID del envío: ",
            validar_entero_positivo_logistica,
            "El ID del envío"
        )

        envio = buscar_envio_por_id(id_envio)  # confirma que el envío existe

        if envio is None:
            print("No existe un envío con ese ID.")
            return

        tramos = listar_tramos_de_envio(id_envio)  # tramos con vehículo y operador, en orden de salida

        print(f"\nEnvío: {id_envio}")
        print(f"Origen general: {envio[3]}")
        print(f"Destino final: {envio[4]}")

        if not tramos:
            print("\nEste envío todavía no tiene tramos.")
            return

        print(f"\nTotal de tramos: {len(tramos)}")

        for numero, tramo in enumerate(tramos, start=1):  # numerados en el orden del recorrido
            print("\n--------------------------------")
            print(f"Tramo {numero} - ID: {tramo[0]}")
            print(f"Vehículo: {tramo[3]} (ID {tramo[2]})")
            print(f"Medio: {tramo[4]}")
            print(f"Origen: {tramo[5]}")
            print(f"Destino: {tramo[6]}")
            print(f"Salida: {formato.fecha_tramo(tramo[7])}")
            print(f"Llegada estimada: {formato.fecha_tramo(tramo[8])}")
            print(
                f"Operador: {tramo[10]} (ID {tramo[9]})"
                if tramo[9] is not None else "Operador: sin asignar"  # los tramos viejos pueden no tener operador
            )

    except Exception as error:
        print(f"Error al consultar tramos: {mensaje_error(error)}")

    finally:
        pausar()