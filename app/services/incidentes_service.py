from datetime import datetime, timezone, timedelta
from math import isfinite

from app.repositories.envio_repository import buscar_envio_por_id
from app.repositories.sensor_repository import listar_sensores
from app.repositories.lectura_iot_repository import consultar_ultima_lectura_db
from app.repositories.incidente_repository import (
    crear_incidente,
    listar_incidentes,
    buscar_incidente,
    actualizar_estado_incidente,
    existe_incidente_por_lectura,
    obtener_o_crear_incidente_iot,
)
from app.repositories.alerta_repository import (
    registrar_alerta,
    listar_alertas,
    actualizar_estado_alerta,
    vincular_incidente_alerta,
)
from app.database.postgres_connection import get_postgres_connection


LIMITES = {
    "temperatura_min": 2.0,
    "temperatura_max": 8.0,
    "humedad_max": 80.0,
    "vibracion_max": 15.0,
    "bateria_min": 20.0,
}


def pedir_id(mensaje):
    while True:
        try:
            numero = int(input(mensaje).strip())
            if numero > 0:
                return numero
        except ValueError:
            pass
        print("Ingresá un ID entero positivo.")


def pausar():
    input("\nPresioná Enter para continuar...")


def mostrar_incidente(fila):
    print("-" * 45)
    print(f"ID: {fila[0]} | Envío: {fila[1]}")
    print(f"Tipo: {fila[2]}")
    print(f"Fecha: {fila[3]}")
    print(f"Severidad: {fila[4]} | Estado: {fila[5]}")
    print(f"Descripción: {fila[6]}")
    if len(fila) >= 9:
        print(f"Ruta: {fila[7]} -> {fila[8]}")


def registrar_incidente_service():
    print("\n--- REGISTRAR INCIDENTE ---")

    try:
        id_envio = pedir_id("ID del envío: ")
        envio = buscar_envio_por_id(id_envio)

        if not envio:
            print("El envío no existe.")
            return

        print(f"Envío {id_envio}: {envio[3]} -> {envio[4]}")

        tipo = input("Tipo de incidente: ").strip()
        if not tipo or len(tipo) > 50:
            print("El tipo debe tener entre 1 y 50 caracteres.")
            return

        print("Severidad: 1. Baja | 2. Media | 3. Alta | 4. Crítica")
        opciones = {
            "1": "Baja",
            "2": "Media",
            "3": "Alta",
            "4": "Crítica",
        }
        severidad = opciones.get(input("Opción: ").strip())

        if severidad is None:
            print("Severidad inválida.")
            return

        descripcion = input("Descripción: ").strip()
        if not descripcion:
            print("La descripción es obligatoria.")
            return

        confirmar = input("¿Registrar incidente? (S/N): ").strip().upper()
        if confirmar != "S":
            print("Operación cancelada.")
            return

        id_incidente = crear_incidente(
            id_envio, tipo, severidad, descripcion
        )

        print(f"\nIncidente registrado. ID: {id_incidente}")
        print("Estado: Abierto")

    except Exception as error:
        print(f"Error al registrar incidente: {error}")
    finally:
        pausar()


def consultar_incidentes_service():
    print("\n--- CONSULTAR INCIDENTES ---")

    try:
        texto = input("ID del envío (Enter = todos): ").strip()
        id_envio = int(texto) if texto else None

        print("Estado: 1. Todos | 2. Abierto | 3. En proceso | 4. Cerrado")
        opcion = input("Opción: ").strip()

        estados = {
            "1": None,
            "2": "Abierto",
            "3": "En proceso",
            "4": "Cerrado",
        }

        if opcion not in estados:
            print("Opción inválida.")
            return

        incidentes = listar_incidentes(id_envio, estados[opcion])
        print(f"\nIncidentes encontrados: {len(incidentes)}")

        for incidente in incidentes:
            mostrar_incidente(incidente)

    except ValueError:
        print("El ID del envío debe ser numérico.")
    except Exception as error:
        print(f"Error al consultar incidentes: {error}")
    finally:
        pausar()


def cambiar_estado_incidente_service():
    print("\n--- ACTUALIZAR INCIDENTE ---")

    try:
        id_incidente = pedir_id("ID del incidente: ")
        incidente = buscar_incidente(id_incidente)

        if incidente is None:
            print("El incidente no existe.")
            return

        mostrar_incidente(incidente)

        if incidente[5] == "Cerrado":
            print("El incidente ya está cerrado.")
            return

        print("1. En proceso")
        print("2. Cerrado")

        opciones = {
            "1": "En proceso",
            "2": "Cerrado",
        }
        estado = opciones.get(input("Opción: ").strip())

        if estado is None:
            print("Opción inválida.")
            return

        if actualizar_estado_incidente(id_incidente, estado):
            print(f"Incidente actualizado a: {estado}")
        else:
            print("No se pudo actualizar.")

    except Exception as error:
        print(f"Error al actualizar incidente: {error}")
    finally:
        pausar()


def detectar_anomalias(lectura):
    """Devuelve las anomalías detectadas en una lectura IoT."""
    resultados = []

    reglas = [
        ("temperatura", "temperatura_min", "menor", "Temperatura baja", "Alta"),
        ("temperatura", "temperatura_max", "mayor", "Temperatura alta", "Alta"),
        ("humedad", "humedad_max", "mayor", "Humedad alta", "Media"),
        ("vibracion", "vibracion_max", "mayor", "Vibración alta", "Alta"),
        ("bateria", "bateria_min", "menor", "Batería baja", "Media"),
    ]

    for campo, limite, comparacion, tipo, severidad in reglas:
        valor = getattr(lectura, campo, None)

        if valor is None:
            continue

        try:
            numero = float(valor)
        except (ValueError, TypeError):
            continue

        if not isfinite(numero):
            continue

        umbral = LIMITES[limite]

        if comparacion == "menor":
            anormal = numero < umbral
        else:
            anormal = numero > umbral

        if anormal:
            resultados.append((
                tipo,
                severidad,
                f"{tipo}: valor {numero:.2f}, límite {umbral:.2f}",
            ))

    return resultados


def buscar_envios_activos_de_contenedor(id_contenedor):
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT e.id_envio
                FROM envio_contenedor ec
                JOIN envio e ON e.id_envio = ec.id_envio
                WHERE ec.id_contenedor = %s
                  AND e.estado NOT IN ('Cancelado', 'Entregado')
                ORDER BY e.id_envio
            """, (id_contenedor,))

            return [fila[0] for fila in cursor.fetchall()]


def obtener_incidente_compatible(
    id_envio, id_sensor, id_lectura, tipo
):
    """
    Recupera incidentes creados por versiones anteriores,
    pero solamente si coinciden con el tipo de anomalía.
    """
    anterior = existe_incidente_por_lectura(
        id_envio,
        id_lectura,
    )

    if anterior is None:
        return None

    incidente = buscar_incidente(anterior)

    if incidente is None:
        return None

    if incidente[1] != id_envio:
        return None

    if incidente[2] != tipo:
        return None

    descripcion = incidente[6] or ""

    if f"Sensor {id_sensor}" not in descripcion:
        return None

    return anterior


def procesar_incidente_de_alerta(
    alerta,
    id_envio,
    id_sensor,
    id_lectura,
    tipo,
    severidad,
    descripcion,
):
    """
    Garantiza un incidente por envío, sensor, lectura y tipo.

    Si la alerta ya estaba vinculada correctamente, reutiliza
    el incidente. Si la vinculación anterior era incorrecta,
    busca o crea el incidente correspondiente.
    """
    id_vinculado = alerta.get("incidente_id")

    if id_vinculado is not None:
        incidente = buscar_incidente(id_vinculado)

        if incidente is not None:
            misma_lectura = (
                f"[lectura:{id_lectura}]" in (incidente[6] or "")
                or f"[iot:{id_sensor}:{id_lectura}:{tipo}]"
                in (incidente[6] or "")
            )

            if (
                incidente[1] == id_envio
                and incidente[2] == tipo
                and misma_lectura
            ):
                return id_vinculado, "reutilizado"

    anterior = obtener_incidente_compatible(
        id_envio,
        id_sensor,
        id_lectura,
        tipo,
    )

    if anterior is not None:
        vincular_incidente_alerta(alerta["_id"], anterior)
        return anterior, "recuperado"

    id_incidente, creado = obtener_o_crear_incidente_iot(
        id_envio,
        id_sensor,
        id_lectura,
        tipo,
        severidad,
        descripcion,
    )

    vincular_incidente_alerta(alerta["_id"], id_incidente)

    accion = "creado" if creado else "reutilizado"
    return id_incidente, accion


def detectar_alertas_service():
    print("\n--- DETECTAR ANOMALÍAS IoT ---")
    print("Se analizará la última lectura de cada sensor activo.")
    print("Umbrales configurados para demostración:")
    print("Temperatura: 2 a 8 °C")
    print("Humedad máxima: 80 %")
    print("Vibración máxima: 15")
    print("Batería mínima: 20 %")

    confirmar = input("\n¿Ejecutar detección? (S/N): ").strip().upper()
    if confirmar != "S":
        return

    try:
        sensores = listar_sensores()

        revisados = 0
        anomalias = 0
        errores = 0

        for sensor in sensores:
            id_sensor = sensor[0]
            id_contenedor = sensor[1]

            if str(sensor[6]).strip().lower() != "activo":
                continue

            try:
                lectura = consultar_ultima_lectura_db(id_sensor)

                if lectura is None:
                    print(f"Sensor {id_sensor}: sin lecturas.")
                    continue

                revisados += 1

                fecha = lectura.fecha_hora

                if fecha.tzinfo is None:
                    fecha = fecha.replace(tzinfo=timezone.utc)

                if fecha < datetime.now(timezone.utc) - timedelta(hours=24):
                    print(f"Sensor {id_sensor}: última lectura antigua.")
                    continue

                detectadas = detectar_anomalias(lectura)

                if not detectadas:
                    print(f"Sensor {id_sensor}: sin anomalías.")
                    continue

                envios = buscar_envios_activos_de_contenedor(
                    id_contenedor
                )

                id_envio = envios[0] if len(envios) == 1 else None

                if len(envios) > 1:
                    print(
                        f"Sensor {id_sensor}: el contenedor tiene "
                        "varios envíos activos. No se crearán "
                        "incidentes automáticos."
                    )

                for tipo, severidad, descripcion in detectadas:
                    try:
                        alerta = registrar_alerta(
                            sensor_id=id_sensor,
                            contenedor_id=id_contenedor,
                            tipo=tipo,
                            severidad=severidad,
                            descripcion=descripcion,
                            lectura_id=lectura.id_lectura,
                            envio_id=id_envio,
                        )

                        anomalias += 1

                        print(
                            f"Sensor {id_sensor}: {descripcion} "
                            f"| Alerta {alerta['_id']}"
                        )

                        if id_envio is None:
                            continue

                        id_incidente, accion = procesar_incidente_de_alerta(
                            alerta=alerta,
                            id_envio=id_envio,
                            id_sensor=id_sensor,
                            id_lectura=lectura.id_lectura,
                            tipo=tipo,
                            severidad=severidad,
                            descripcion=descripcion,
                        )

                        print(
                            f"  Incidente {id_incidente} "
                            f"{accion} para {tipo}."
                        )

                    except Exception as error:
                        errores += 1
                        print(
                            f"Sensor {id_sensor}, anomalía {tipo}: "
                            f"error: {error}"
                        )

            except Exception as error:
                errores += 1
                print(f"Sensor {id_sensor}: error: {error}")

        print("\n--- RESULTADO ---")
        print(f"Sensores revisados: {revisados}")
        print(f"Anomalías encontradas: {anomalias}")
        print(f"Errores: {errores}")
        print(
            "Las alertas repetidas de una misma lectura "
            "se reutilizan en MongoDB."
        )

    except Exception as error:
        print(f"Error en la detección: {error}")
    finally:
        pausar()


def consultar_alertas_service():
    print("\n--- CONSULTAR ALERTAS ---")

    try:
        print("1. Todas | 2. Activas | 3. Atendidas")

        opciones = {
            "1": None,
            "2": "Activa",
            "3": "Atendida",
        }

        opcion = input("Opción: ").strip()

        if opcion not in opciones:
            print("Opción inválida.")
            return

        texto = input("ID sensor (Enter = todos): ").strip()
        sensor_id = int(texto) if texto else None

        alertas = listar_alertas(opciones[opcion], sensor_id)
        print(f"\nAlertas encontradas: {len(alertas)}")

        for alerta in alertas:
            print("-" * 45)
            print(f"ID: {alerta['_id']}")
            print(f"Sensor: {alerta.get('sensor_id')}")
            print(f"Envío: {alerta.get('envio_id')}")
            print(f"Tipo: {alerta.get('tipo')}")
            print(f"Severidad: {alerta.get('severidad')}")
            print(f"Estado: {alerta.get('estado')}")
            print(f"Fecha: {alerta.get('fecha')}")
            print(f"Descripción: {alerta.get('descripcion')}")
            print(f"Incidente: {alerta.get('incidente_id')}")

    except ValueError:
        print("El ID del sensor debe ser numérico.")
    except Exception as error:
        print(f"Error al consultar alertas: {error}")
    finally:
        pausar()


def atender_alerta_service():
    print("\n--- MARCAR ALERTA COMO ATENDIDA ---")

    try:
        id_alerta = input("ID de la alerta: ").strip()

        if actualizar_estado_alerta(id_alerta, "Atendida"):
            print("Alerta marcada como atendida.")
        else:
            print("No se encontró la alerta.")

    except Exception as error:
        print(f"Error al actualizar alerta: {error}")
    finally:
        pausar()