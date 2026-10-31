from datetime import datetime, timezone

from app.repositories.envio_repository import buscar_envio_por_id
from app.repositories.contenedor_repository import (
    buscar_contenedor_por_id
)
from app.repositories.tramo_repository import listar_tramos_de_envio
from app.repositories.evento_repository import (
    insertar_evento,
    listar_eventos_envio,
    listar_eventos_envios,
    tipos_registrados,
    listar_pendientes,
    registrar_pendiente_estado,
    listar_pendientes_estado,
    resolver_pendiente_estado
)
from app.repositories.trazabilidad_repository import (
    actualizar_estado_envio,
    listar_envios_de_contenedor
)
from app.repositories.grafo_repository import (
    obtener_ruta_envio,
    operadores_de_contenedor,
    red_operadores_cliente
)
from app.repositories.recorrido_repository import (
    consultar_gps_contenedor
)

from app.services.autenticacion import obtener_sesion_actual
from app.services.sincronizacion_service import (
    sincronizar_envio_neo4j,
    reconciliar_envio,
    reparar_pendientes,
    resincronizar_todos
)

from app.utils.logger import obtener_logger
from app.utils.validaciones_logistica import (
    validar_texto,
    validar_entero_positivo_logistica,
    normalizar
)
from app.utils.validaciones_trazabilidad import (
    ZONA_ARGENTINA,
    TIPOS_EVENTO,
    DETALLE_POR_TIPO,
    parsear_fecha_hora,
    validar_coordenada,
    validar_texto_opcional,
    validar_numero_opcional,
    validar_evento_permitido,
    estado_nuevo_por_evento,
    ultimos_meses,
    muestrear,
    fusionar_recorrido
)


logger = obtener_logger("trazabilidad")

MAX_PUNTOS_GPS_MOSTRADOS = 25


# ------------------------------------------------------------------
# Utilidades de interfaz
# ------------------------------------------------------------------

def pedir(mensaje, funcion, *args):
    while True:
        try:
            return funcion(input(mensaje), *args)
        except ValueError as error:
            print(f"Error: {error}")


def pausar():
    input("\nPresione Enter para continuar...")


def formatear_fecha(fecha):
    if fecha is None:
        return "-"

    if fecha.tzinfo is None:
        fecha = fecha.replace(tzinfo=timezone.utc)

    return fecha.astimezone(ZONA_ARGENTINA).strftime("%Y-%m-%d %H:%M")


def formatear_duracion(delta):
    segundos = int(delta.total_seconds())
    signo = "-" if segundos < 0 else ""
    segundos = abs(segundos)

    dias, resto = divmod(segundos, 86400)
    horas, resto = divmod(resto, 3600)
    minutos = resto // 60

    if dias:
        return f"{signo}{dias} d {horas} h"

    if horas:
        return f"{signo}{horas} h {minutos} min"

    return f"{signo}{minutos} min"


def pedir_envio():
    id_envio = pedir(
        "ID del envío: ",
        validar_entero_positivo_logistica,
        "El ID del envío"
    )

    envio = buscar_envio_por_id(id_envio)

    if envio is None:
        print("No existe un envío con ese ID.")
        return None

    return envio


def mostrar_evento(numero, evento):
    ubicacion = evento.get("ubicacion") or {}
    print("--------------------------------")
    print(f"{numero}. {evento['tipo']}")
    print(f"   Fecha: {formatear_fecha(evento['fecha_hora'])}")
    print(f"   Ubicación: {ubicacion.get('nombre', '-')}")

    if "lat" in ubicacion and "lon" in ubicacion:
        print(
            f"   Coordenadas: {ubicacion['lat']}, {ubicacion['lon']}"
        )

    print(f"   Descripción: {evento.get('descripcion', '-')}")

    for clave, valor in (evento.get("detalle") or {}).items():
        print(f"   {clave}: {valor}")


# ------------------------------------------------------------------
# 1. Registrar evento logístico (MongoDB)
# ------------------------------------------------------------------

def elegir_tipo_evento():
    print("\nTipo de evento:")

    for numero, tipo in enumerate(TIPOS_EVENTO, start=1):
        print(f"{numero}. {tipo}")

    print("0. Cancelar")

    while True:
        opcion = input("Opción: ").strip()

        if opcion == "0":
            return None

        if opcion.isdigit() and 1 <= int(opcion) <= len(TIPOS_EVENTO):
            return TIPOS_EVENTO[int(opcion) - 1]

        print("Error: seleccione una opción de la lista.")


def pedir_detalle(tipo):
    detalle = {}

    for campo, clase in DETALLE_POR_TIPO.get(tipo, []):
        etiqueta = campo.replace("_", " ").capitalize()

        if clase == "numero":
            valor = pedir(
                f"{etiqueta} (Enter para omitir): ",
                validar_numero_opcional,
                etiqueta
            )
        else:
            valor = pedir(
                f"{etiqueta} (Enter para omitir): ",
                validar_texto_opcional,
                etiqueta
            )

        if valor is not None:
            detalle[campo] = valor

    return detalle


def registrar_evento_service():
    print("\n--- REGISTRAR EVENTO LOGÍSTICO ---")

    try:
        envio = pedir_envio()

        if envio is None:
            return

        id_envio = envio[0]

        print(
            f"\nEnvío {id_envio} | Cliente: {envio[2]} | "
            f"Estado: {envio[5]}"
        )

        tipo = elegir_tipo_evento()

        if tipo is None:
            print("Operación cancelada.")
            return

        try:
            advertencias = validar_evento_permitido(
                envio[5], tipo, tipos_registrados(id_envio)
            )
        except ValueError as error:
            print(f"\nNo se puede registrar el evento: {error}")
            return

        for advertencia in advertencias:
            print(f"Advertencia: {advertencia}")

        fecha_hora = pedir(
            "Fecha y hora AAAA-MM-DD HH:MM "
            "(hora argentina, Enter = ahora): ",
            parsear_fecha_hora
        )

        # La fecha del evento ENTREGADO es la fecha real de entrega; no
        # puede ser anterior a la creación del envío (CHECK de la 013).
        if tipo == "ENTREGADO" and envio[7] and fecha_hora < envio[7]:
            print(
                "\nLa entrega no puede ser anterior a la creación del envío "
                f"({formatear_fecha(envio[7])})."
            )
            return

        ubicacion = {
            "nombre": pedir(
                "Ubicación: ", validar_texto, "La ubicación", 150
            )
        }

        latitud = pedir(
            "Latitud (Enter para omitir): ",
            validar_coordenada, "La latitud", -90, 90
        )
        longitud = pedir(
            "Longitud (Enter para omitir): ",
            validar_coordenada, "La longitud", -180, 180
        )

        if latitud is not None and longitud is not None:
            ubicacion["lat"] = latitud
            ubicacion["lon"] = longitud

        descripcion = pedir(
            "Descripción: ", validar_texto, "La descripción", 500
        )

        detalle = pedir_detalle(tipo)

        confirmacion = input(
            f"\n¿Registrar evento {tipo} para el envío "
            f"{id_envio}? (S/N): "
        ).strip().upper()

        if confirmacion != "S":
            print("Registro cancelado.")
            return

        usuario = obtener_sesion_actual()

        documento = {
            "envio_id": id_envio,
            "tipo": tipo,
            "fecha_hora": fecha_hora,
            "ubicacion": ubicacion,
            "descripcion": descripcion,
            "usuario_id": usuario["id_usuario"] if usuario else None,
            "detalle": detalle,
            "fecha_registro": datetime.now(timezone.utc)
        }

        id_evento = insertar_evento(documento)
        logger.info(
            "Evento %s registrado para el envío %s (id %s)",
            tipo, id_envio, id_evento
        )

        print("\nEvento registrado correctamente.")

        nuevo_estado = estado_nuevo_por_evento(tipo, envio[5])

        if nuevo_estado:
            # La fecha real de entrega es la del evento ENTREGADO.
            fecha_entrega = fecha_hora if tipo == "ENTREGADO" else None
            try:
                if not actualizar_estado_envio(
                    id_envio, nuevo_estado, fecha_entrega
                ):
                    raise RuntimeError(
                        "No se encontró el envío o ya estaba Entregado"
                    )
                if fecha_entrega is not None:
                    print(
                        "Fecha real de entrega registrada: "
                        f"{formatear_fecha(fecha_entrega)}"
                    )
                print(f"Estado del envío actualizado a: {nuevo_estado}")
                sincronizar_envio_neo4j(id_envio)
            except Exception as error:
                logger.error(
                    "Evento %s guardado pero no se pudo actualizar el "
                    "estado del envío %s: %s",
                    id_evento, id_envio, error
                )
                try:
                    registrar_pendiente_estado(
                        id_envio, nuevo_estado, id_evento, error,
                        fecha_entrega=fecha_entrega,
                    )
                    print("\nAdvertencia: evento guardado; la actualización del estado quedó pendiente.")
                except Exception as error_pendiente:
                    logger.exception("No se pudo persistir el pendiente de estado: %s", error_pendiente)
                    print("\nADVERTENCIA: estado no actualizado y pendiente no guardado. Revisar logs/app.log.")

    except Exception as error:
        logger.exception("Error al registrar evento: %s", error)
        print(f"\nError al registrar el evento: {error}")

    finally:
        pausar()


# ------------------------------------------------------------------
# 2. Historial completo de un envío (MongoDB)
# ------------------------------------------------------------------

def historial_envio_service(envio=None):
    """envio: fila ya verificada (portal del cliente); si falta, se pide."""
    print("\n--- HISTORIAL DE EVENTOS DE UN ENVÍO ---")

    try:
        envio = envio or pedir_envio()

        if envio is None:
            return

        eventos = listar_eventos_envio(envio[0])

        print(
            f"\nEnvío {envio[0]} | {envio[3]} -> {envio[4]} | "
            f"Estado: {envio[5]}"
        )

        if not eventos:
            print("\nEl envío todavía no tiene eventos registrados.")
            return

        print(f"\nTotal de eventos: {len(eventos)}")

        for numero, evento in enumerate(eventos, start=1):
            mostrar_evento(numero, evento)

    except Exception as error:
        logger.exception("Error al consultar historial: %s", error)
        print(f"\nError al consultar el historial: {error}")

    finally:
        pausar()


# ------------------------------------------------------------------
# 3. Seguimiento temporal (PostgreSQL + MongoDB)
# ------------------------------------------------------------------

def seguimiento_temporal_service(envio=None):
    """envio: fila ya verificada (portal del cliente); si falta, se pide."""
    print("\n--- SEGUIMIENTO TEMPORAL DE UN ENVÍO ---")

    try:
        envio = envio or pedir_envio()

        if envio is None:
            return

        ahora = datetime.now(timezone.utc)
        eventos = listar_eventos_envio(envio[0])
        tramos = listar_tramos_de_envio(envio[0])
        estado = envio[5]

        print(f"\nEnvío {envio[0]} | Cliente: {envio[2]}")
        print(f"Ruta general: {envio[3]} -> {envio[4]}")
        print(f"Estado actual: {estado}")
        print(f"Creado: {formatear_fecha(envio[7])}")
        print(f"Tiempo desde la creación: {formatear_duracion(ahora - envio[7])}")

        if tramos:
            fechas_llegada = [t[8] for t in tramos if t[8] is not None]
            llegada = max(fechas_llegada) if fechas_llegada else None
            print(f"Llegada estimada (último tramo): {formatear_fecha(llegada)}")

            if llegada and normalizar(estado) not in ("entregado", "cancelado"):
                if ahora > llegada:
                    print(
                        "SITUACIÓN: DEMORADO por "
                        f"{formatear_duracion(ahora - llegada)}"
                    )
                else:
                    print(
                        "SITUACIÓN: en plazo "
                        f"(faltan {formatear_duracion(llegada - ahora)})"
                    )
        else:
            print("El envío todavía no tiene tramos planificados.")

        if not eventos:
            print("\nNo hay eventos registrados.")
            return

        print("\nLínea de tiempo:")
        anterior = None

        for evento in eventos:
            fecha = evento["fecha_hora"]
            ubicacion = (evento.get("ubicacion") or {}).get("nombre", "-")
            salto = ""

            if anterior is not None:
                salto = f"  (+{formatear_duracion(fecha - anterior)})"

            print(
                f"  {formatear_fecha(fecha)}  {evento['tipo']:<15} "
                f"{ubicacion}{salto}"
            )
            anterior = fecha

        ultimo = eventos[-1]
        print(
            f"\nÚltimo evento: {ultimo['tipo']} hace "
            f"{formatear_duracion(ahora - ultimo['fecha_hora'])}"
        )

        if ultimo["tipo"] == "ENTREGADO":
            print(
                "Duración total (primer evento -> entrega): "
                f"{formatear_duracion(ultimo['fecha_hora'] - eventos[0]['fecha_hora'])}"
            )

    except Exception as error:
        logger.exception("Error en seguimiento temporal: %s", error)
        print(f"\nError en el seguimiento temporal: {error}")

    finally:
        pausar()


# ------------------------------------------------------------------
# 4. Ruta completa de un envío (Neo4j)
# ------------------------------------------------------------------

def ruta_completa_service(envio=None):
    """envio: fila ya verificada (portal del cliente); si falta, se pide."""
    print("\n--- RUTA COMPLETA DE UN ENVÍO ---")

    try:
        envio = envio or pedir_envio()

        if envio is None:
            return

        filas = obtener_ruta_envio(envio[0])

        if not filas:
            print(
                "\nEl envío no está en el grafo. Use la opción "
                "'Sincronizar o reparar' del menú de trazabilidad."
            )
            return

        cabecera = filas[0]
        print(
            f"\nEnvío {cabecera['id_envio']} | "
            f"Cliente: {cabecera['cliente']} | "
            f"Estado: {cabecera['estado']}"
        )
        print(
            f"Origen: {cabecera['origen_envio']} | "
            f"Destino final: {cabecera['destino_envio']}"
        )

        tramos = [f for f in filas if f["id_tramo"] is not None]

        if not tramos:
            print("\nEl envío no tiene tramos en el grafo.")
            return

        print("\nRecorrido:")

        for numero, fila in enumerate(tramos, start=1):
            print(
                f"{numero}. {fila['origen_tramo']} -> "
                f"{fila['destino_tramo']}  "
                f"[{fila['medio']}, vehículo {fila['vehiculo']}, "
                f"operador {fila['operador'] or 'sin datos'}]"
            )
            print(
                f"   Salida: {(fila['salida'] or '-')[:16].replace('T', ' ')} | "
                f"Llegada estimada: "
                f"{(fila['llegada'] or '-')[:16].replace('T', ' ')}"
            )

        print(
            "\nCamino: "
            + " -> ".join(
                [tramos[0]["origen_tramo"]]
                + [t["destino_tramo"] for t in tramos]
            )
        )

    except Exception as error:
        logger.exception("Error al consultar la ruta: %s", error)
        print(f"\nError al consultar la ruta: {error}")

    finally:
        pausar()


# ------------------------------------------------------------------
# 5. Recorrido de un contenedor (PostgreSQL + MongoDB + Cassandra)
# ------------------------------------------------------------------

def pedir_cantidad_meses():
    while True:
        texto = input(
            "Meses hacia atrás a consultar (1-12, Enter = 3): "
        ).strip()

        if not texto:
            return 3

        if texto.isdigit() and 1 <= int(texto) <= 12:
            return int(texto)

        print("Error: ingrese un número entre 1 y 12.")


def recorrido_contenedor_service():
    print("\n--- RECORRIDO DE UN CONTENEDOR ---")

    try:
        id_contenedor = pedir(
            "ID del contenedor: ",
            validar_entero_positivo_logistica,
            "El ID del contenedor"
        )

        contenedor = buscar_contenedor_por_id(id_contenedor)

        if contenedor is None:
            print("No existe un contenedor con ese ID.")
            return

        print(f"\nContenedor {contenedor[0]} | Código: {contenedor[1]}")

        envios = listar_envios_de_contenedor(id_contenedor)

        if envios:
            print("Envíos asociados:")
            for envio in envios:
                print(
                    f"  Envío {envio[0]} | {envio[2]} -> {envio[3]} | "
                    f"{envio[1]}"
                )
        else:
            print("El contenedor no está asociado a ningún envío.")

        meses = ultimos_meses(pedir_cantidad_meses())

        eventos = listar_eventos_envios([e[0] for e in envios])
        puntos = consultar_gps_contenedor(id_contenedor, meses)

        linea = fusionar_recorrido(eventos, puntos)

        if not linea:
            print(
                "\nNo hay eventos ni posiciones GPS para ese período."
            )
            return

        gps = [item for item in linea if item["origen"] == "GPS"]
        gps_mostrados = set(
            id(item) for item in muestrear(gps, MAX_PUNTOS_GPS_MOSTRADOS)
        )

        print(
            f"\nEventos: {len(eventos)} | Posiciones GPS: {len(puntos)} "
            f"(se muestran {len(gps_mostrados)})"
        )
        print("\nLínea de tiempo (eventos de envíos asociados actualmente y GPS de los meses seleccionados):")

        for item in linea:
            if item["origen"] == "GPS" and id(item) not in gps_mostrados:
                continue

            print(
                f"  {formatear_fecha(item['fecha'])}  "
                f"{item['origen']:<6} {item['texto']}"
            )

    except Exception as error:
        logger.exception("Error al reconstruir recorrido: %s", error)
        print(f"\nError al reconstruir el recorrido: {error}")

    finally:
        pausar()


# ------------------------------------------------------------------
# 6. Sincronizar o reparar la proyección (PostgreSQL -> Neo4j)
# ------------------------------------------------------------------

def sincronizar_proyeccion_service():
    print("\n--- SINCRONIZAR / REPARAR LA RED DE RUTAS ---")

    try:
        pendientes = listar_pendientes()
        print(f"Pendientes de sincronización: {len(pendientes)}")

        for pendiente in pendientes:
            print(
                f"  Envío {pendiente['envio_id']} | intentos: "
                f"{pendiente.get('intentos', 0)} | "
                f"error: {pendiente.get('ultimo_error', '-')}"
            )

        estados_pendientes = listar_pendientes_estado()
        print(f"Actualizaciones de estado pendientes: {len(estados_pendientes)}")
        print("\n1. Reintentar actualizaciones pendientes de la red de rutas")
        print("2. Resincronizar un envío")
        print("3. Resincronizar todos los envíos")
        print("4. Reintentar cambios de estado pendientes")
        print("0. Volver")

        opcion = input("\nOpción: ").strip()

        if opcion == "1":
            resueltos, fallidos = reparar_pendientes()
            print(f"\nResueltos: {resueltos} | Fallidos: {len(fallidos)}")

            for id_envio, error in fallidos:
                print(f"  Envío {id_envio}: {error}")

        elif opcion == "2":
            id_envio = pedir(
                "ID del envío: ",
                validar_entero_positivo_logistica,
                "El ID del envío"
            )
            sincronizar_envio_neo4j(id_envio)
            print("\nFinalizó el intento de sincronización.")

        elif opcion == "3":
            correctos, errores = resincronizar_todos()
            print(
                f"\nSincronizados: {correctos} | Con error: {len(errores)}"
            )

            for id_envio, error in errores:
                print(f"  Envío {id_envio}: {error}")

        elif opcion == "4":
            ok, fallos = 0, 0
            for pendiente in listar_pendientes_estado():
                try:
                    if not actualizar_estado_envio(
                        pendiente["envio_id"], pendiente["estado"],
                        fecha_entrega_de_pendiente(pendiente),
                    ):
                        raise ValueError(
                            "El envío ya no existe o ya está Entregado"
                        )
                    resolver_pendiente_estado(pendiente["evento_id"])
                    sincronizar_envio_neo4j(pendiente["envio_id"])
                    ok += 1
                except Exception as error:
                    fallos += 1
                    logger.exception("Error al reparar estado de envío %s: %s", pendiente["envio_id"], error)
            print(f"Estados reparados: {ok} | Con error: {fallos}")
        elif opcion != "0":
            print("Opción inválida.")

    except Exception as error:
        logger.exception("Error al sincronizar: %s", error)
        print(f"\nError al sincronizar: {error}")

    finally:
        pausar()


# ------------------------------------------------------------------
# 7 y 8. Operadores en la red (Neo4j)
# ------------------------------------------------------------------

def fecha_entrega_de_pendiente(pendiente):
    """Fecha real de entrega de un estado pendiente de aplicar.

    Usa la guardada en el pendiente; si es un pendiente anterior que no la
    tiene, la toma del evento ENTREGADO original en MongoDB.
    """
    if str(pendiente.get("estado", "")).strip().casefold() != "entregado":
        return None
    if pendiente.get("fecha_entrega") is not None:
        return pendiente["fecha_entrega"]
    for evento in listar_eventos_envio(pendiente["envio_id"]):
        if str(evento.get("_id")) == str(pendiente.get("evento_id")):
            return evento.get("fecha_hora")
    raise ValueError(
        "No se encontró el evento ENTREGADO para obtener la fecha de entrega."
    )


def cliente_visible(sesion):
    """Cliente al que se restringen las consultas, o None si ve todo.

    Depende de la PARTE del usuario, no de su nivel de permisos:
    - Usuario de un cliente: solo los datos de su cliente.
    - Usuario de proveedor u operador: no accede a datos de clientes.
    - Usuario interno (sin parte): todos.
    """
    if sesion is None:
        raise PermissionError("Debe iniciar sesión.")

    if sesion.get("id_cliente") is not None:
        return sesion["id_cliente"]

    if (
        sesion.get("id_proveedor") is not None
        or sesion.get("id_operador") is not None
    ):
        raise PermissionError(
            "Los usuarios de proveedores u operadores no consultan "
            "datos de clientes."
        )

    return None


def quien_llevo_contenedor_service():
    print("\n--- ¿QUIÉN LLEVÓ EL CONTENEDOR? ---")

    try:
        restringido = cliente_visible(obtener_sesion_actual())

        id_contenedor = pedir(
            "ID del contenedor: ",
            validar_entero_positivo_logistica,
            "El ID del contenedor"
        )

        filas = operadores_de_contenedor(id_contenedor, restringido)

        if not filas:
            print(
                "\nNo hay tramos para ese contenedor"
                + (" en sus envíos." if restringido else ".")
                + " Si los datos son nuevos, sincronice la red de rutas (opción 6)."
            )
            return

        for fila in filas:
            print(
                f"Envío {fila['id_envio']} ({fila['cliente']}) | "
                f"Tramo {fila['id_tramo']} | {fila['medio']} | "
                f"{fila['origen']} -> {fila['destino']} | "
                f"Salida {(fila['salida'] or '-')[:10]} | "
                f"Operador: {fila['operador'] or 'sin asignar'}"
            )

    except PermissionError as error:
        print(f"\n{error}")
    except Exception as error:
        logger.exception("Error al consultar operadores del contenedor")
        print(f"\nError al consultar la red de operadores: {error}")

    finally:
        pausar()


def red_operadores_cliente_service():
    print("\n--- RED CLIENTE - OPERADORES - ENVÍOS ---")

    try:
        restringido = cliente_visible(obtener_sesion_actual())

        if restringido is not None:
            id_cliente = restringido
        else:
            id_cliente = pedir(
                "ID del cliente: ",
                validar_entero_positivo_logistica,
                "El ID del cliente"
            )

        filas = red_operadores_cliente(id_cliente)

        if not filas:
            print(
                "\nNingún envío del cliente tiene tramos con operador en "
                "el grafo."
            )
            return

        for fila in filas:
            print(
                f"{fila['operador']} ({', '.join(fila['modalidades'] or [])}) "
                f"| Envíos del cliente: "
                f"{', '.join(str(e) for e in fila['envios'])} "
                f"| Otros clientes que usan este operador: "
                f"{fila['otros_clientes']}"
            )

    except PermissionError as error:
        print(f"\n{error}")
    except Exception as error:
        logger.exception("Error al consultar la red del cliente")
        print(f"\nError al consultar la red de operadores: {error}")

    finally:
        pausar()
