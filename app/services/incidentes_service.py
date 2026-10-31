from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

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
from app.repositories.lectura_iot_repository import ultimas_lecturas_sensor
from app.repositories.regla_alerta_repository import VARIABLES, reglas_vigentes, umbral
from app.services.alertas_service import emitir_alerta
from app.services.deteccion_sensores import (
    es_lectura_valida_para_umbrales,
    evaluar_umbrales,
    fallas_de_sensor,
)


# Los umbrales están en la tabla regla_alerta (ABM de reglas de alerta).
ZONA_ARGENTINA = ZoneInfo("America/Argentina/Buenos_Aires")


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


def detectar_anomalias(lectura, vigentes=None):
    """Anomalías de la carga en una lectura, según las reglas de alerta activas.

    Devuelve [(tipo, severidad, descripción)]. Si la lectura tiene valores
    físicamente imposibles no se evalúa (es una falla del sensor).
    """
    if vigentes is None:
        vigentes = reglas_vigentes()
    if not es_lectura_valida_para_umbrales(lectura):
        return []
    return evaluar_umbrales(lectura, vigentes)


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


def _texto_umbrales(vigentes):
    lineas = []
    for (variable, limite), reglas in sorted(vigentes.items()):
        nombre, unidad = VARIABLES[variable][0], VARIABLES[variable][1]
        signo = "menor a" if limite == "MIN" else "mayor a"
        for valor, severidad, _ in sorted(reglas):
            lineas.append(f"  {nombre} {signo} {valor:g} {unidad} -> {severidad}".rstrip())
    return lineas


def revisar_lecturas_sensores(ahora=None, horas_vigencia=24):
    """Revisa las lecturas recientes de cada sensor activo y emite alertas.

    - Umbrales de la carga sobre la última lectura (crea incidente si el
      contenedor tiene un único envío activo).
    - Fallas del sensor (valor imposible, congelado, salto brusco): alerta
      y mensaje, sin incidente (falla el equipo, no la carga).
    Sin interacción: la usan el menú, el proceso periódico y la carga demo.
    """
    ahora = ahora or datetime.now(timezone.utc)
    vigentes = reglas_vigentes()
    congeladas = umbral(vigentes, "lecturas_congeladas", "MAX", 6)
    cantidad = max(10, int(congeladas))
    resumen = {"revisados": 0, "sin_lecturas": 0, "antiguas": 0, "anomalias": 0,
               "fallas": 0, "alertas_nuevas": 0, "mensajes": 0, "incidentes": 0,
               "detalle": [], "errores": []}

    for sensor in listar_sensores():
        id_sensor, id_contenedor = sensor[0], sensor[1]
        if str(sensor[6]).strip().lower() != "activo":
            continue
        try:
            lecturas = ultimas_lecturas_sensor(id_sensor, cantidad, ahora)
            if not lecturas:
                resumen["sin_lecturas"] += 1
                continue
            resumen["revisados"] += 1
            limite = ahora - timedelta(hours=horas_vigencia)
            recientes = [l for l in lecturas
                         if (l.fecha_hora if l.fecha_hora.tzinfo else
                             l.fecha_hora.replace(tzinfo=timezone.utc)) >= limite]
            if not recientes:
                resumen["antiguas"] += 1
                continue

            envios = buscar_envios_activos_de_contenedor(id_contenedor)
            id_envio = envios[0] if len(envios) == 1 else None
            ultima = recientes[0]

            for tipo, severidad, descripcion, id_lectura in fallas_de_sensor(recientes, vigentes):
                alerta = emitir_alerta(
                    sensor_id=id_sensor, contenedor_id=id_contenedor, tipo=tipo,
                    severidad=severidad, descripcion=descripcion,
                    lectura_id=id_lectura, envio_id=id_envio)
                resumen["fallas"] += 1
                resumen["alertas_nuevas"] += bool(alerta.get("nueva"))
                resumen["mensajes"] += alerta.get("mensajes_creados", 0)
                resumen["detalle"].append((id_sensor, tipo, descripcion, None))

            for tipo, severidad, descripcion in detectar_anomalias(ultima, vigentes):
                alerta = emitir_alerta(
                    sensor_id=id_sensor, contenedor_id=id_contenedor, tipo=tipo,
                    severidad=severidad, descripcion=descripcion,
                    lectura_id=ultima.id_lectura, envio_id=id_envio)
                resumen["anomalias"] += 1
                resumen["alertas_nuevas"] += bool(alerta.get("nueva"))
                resumen["mensajes"] += alerta.get("mensajes_creados", 0)
                id_incidente = None
                if id_envio is not None:
                    id_incidente, _ = procesar_incidente_de_alerta(
                        alerta=alerta, id_envio=id_envio, id_sensor=id_sensor,
                        id_lectura=ultima.id_lectura, tipo=tipo,
                        severidad=severidad, descripcion=descripcion)
                    resumen["incidentes"] += 1
                resumen["detalle"].append((id_sensor, tipo, descripcion, id_incidente))
        except Exception as error:
            resumen["errores"].append((id_sensor, str(error)))
    return resumen


def detectar_alertas_service():
    print("\n--- DETECTAR ANOMALÍAS Y FALLAS DE SENSORES ---")
    print("Se analizan las lecturas de las últimas 24 horas de cada sensor activo.")
    try:
        vigentes = reglas_vigentes()
        print("Reglas de alerta activas:")
        for linea in _texto_umbrales(vigentes):
            print(linea)
        print("También se detectan fallas del sensor: valores imposibles, "
              "lecturas congeladas y saltos bruscos.")
    except Exception as error:
        print(f"No se pudieron leer las reglas de alerta: {error}")
        pausar()
        return

    confirmar = input("\n¿Ejecutar detección? (S/N): ").strip().upper()
    if confirmar != "S":
        return

    try:
        resumen = revisar_lecturas_sensores()
        for id_sensor, tipo, descripcion, id_incidente in resumen["detalle"]:
            extra = f" | incidente {id_incidente}" if id_incidente else ""
            print(f"Sensor {id_sensor}: {descripcion}{extra}")
        for id_sensor, error in resumen["errores"]:
            print(f"Sensor {id_sensor}: error: {error}")

        print("\n--- RESULTADO ---")
        print(f"Sensores revisados: {resumen['revisados']}")
        print(f"Sin lecturas en las últimas 24 horas: {resumen['antiguas']}")
        print(f"Anomalías de la carga: {resumen['anomalias']}")
        print(f"Fallas de sensor: {resumen['fallas']}")
        print(f"Alertas nuevas: {resumen['alertas_nuevas']} "
              f"(mensajes enviados: {resumen['mensajes']})")
        print(f"Errores: {len(resumen['errores'])}")
        print("Si una alerta ya existía no se repite ni se vuelve a notificar.")
    except Exception as error:
        print(f"Error en la detección: {error}")
    finally:
        pausar()


def _fecha_alerta(fecha):
    if fecha is None:
        return "-"
    if fecha.tzinfo is None:
        fecha = fecha.replace(tzinfo=timezone.utc)
    return fecha.astimezone(ZONA_ARGENTINA).strftime("%d/%m/%Y %H:%M")


def mostrar_alerta(alerta, numero):
    print("-" * 45)
    print(f"{numero}. {alerta.get('tipo')} | {alerta.get('severidad')} | "
          f"{alerta.get('estado')} | {_fecha_alerta(alerta.get('fecha'))}")
    lugar = [f"Sensor {alerta.get('sensor_id')}"]
    if alerta.get("envio_id") is not None:
        lugar.append(f"envío {alerta['envio_id']}")
    if alerta.get("incidente_id") is not None:
        lugar.append(f"incidente {alerta['incidente_id']}")
    print("   " + " | ".join(lugar))
    print(f"   {alerta.get('descripcion')}")
    if alerta.get("nota_atencion"):
        print(f"   Nota: {alerta['nota_atencion']}")


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

        texto = input("N.º de sensor (Enter = todos): ").strip()
        sensor_id = int(texto) if texto else None

        alertas = listar_alertas(opciones[opcion], sensor_id)
        print(f"\nAlertas encontradas: {len(alertas)}")

        for numero, alerta in enumerate(alertas, 1):
            mostrar_alerta(alerta, numero)

    except ValueError:
        print("El número de sensor debe ser numérico.")
    except Exception as error:
        print(f"Error al consultar alertas: {error}")
    finally:
        pausar()


def atender_alerta_service():
    print("\n--- MARCAR ALERTA COMO ATENDIDA ---")

    try:
        alertas = listar_alertas("Activa")

        if not alertas:
            print("No hay alertas activas.")
            return

        for numero, alerta in enumerate(alertas, 1):
            mostrar_alerta(alerta, numero)

        valor = input("\nNúmero de alerta (0 = cancelar): ").strip()

        if not valor.isdigit() or not 1 <= int(valor) <= len(alertas):
            print("Cancelado.")
            return

        if actualizar_estado_alerta(str(alertas[int(valor) - 1]["_id"]), "Atendida"):
            print("Alerta marcada como atendida.")
        else:
            print("No se encontró la alerta.")

    except Exception as error:
        print(f"Error al actualizar alerta: {error}")
    finally:
        pausar()
