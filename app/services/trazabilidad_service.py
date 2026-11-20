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
    listar_envios_de_contenedor,
    registrar_evento_y_estado
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
    resincronizar_envio,
    resincronizar_todos
)

from app.utils.logger import obtener_logger
from app.utils.validaciones_logistica import (
    validar_texto,
    validar_entero_positivo_logistica,
    normalizar
)
from app.utils import formato
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
from app.utils.errores import mensaje_error
from app.services.autenticacion import requiere_permiso


logger = obtener_logger("trazabilidad")  # registro en logs/app.log

MAX_PUNTOS_GPS_MOSTRADOS = 25  # para no llenar la pantalla de puntos GPS


# ------------------------------------------------------------------
# Utilidades de interfaz
# ------------------------------------------------------------------

def pedir(mensaje, funcion, *args):  # repite la pregunta hasta que la validación pase
    while True:
        try:
            return funcion(input(mensaje), *args)
        except ValueError as error:
            print(f"Error: {mensaje_error(error)}")


def pausar():
    input("\nPresioná Enter para continuar...")


def formatear_fecha(fecha):  # fecha en hora argentina para mostrar
    if fecha is None:
        return "-"

    if fecha.tzinfo is None:
        fecha = fecha.replace(tzinfo=timezone.utc)

    return fecha.astimezone(ZONA_ARGENTINA).strftime("%d/%m/%Y %H:%M")


def formatear_duracion(delta):  # duración en días, horas o minutos; la usa el seguimiento temporal
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


def pedir_envio():  # pide un ID y busca el envío en PostgreSQL; la usan las opciones 1 a 4
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


def mostrar_evento(numero, evento):  # imprime un evento de MongoDB; la usa el historial
    ubicacion = evento.get("ubicacion") or {}
    print("--------------------------------")
    print(f"{numero}. {formato.evento(evento['tipo'])}")
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

def elegir_tipo_evento():  # elige el tipo de evento; la usa registrar evento
    print("\nTipo de evento:")

    for numero, tipo in enumerate(TIPOS_EVENTO, start=1):
        print(f"{numero}. {formato.evento(tipo)}")

    print("0. Cancelar")

    while True:
        opcion = input("Opción: ").strip()

        if opcion == "0":
            return None

        if opcion.isdigit() and 1 <= int(opcion) <= len(TIPOS_EVENTO):
            return TIPOS_EVENTO[int(opcion) - 1]

        print("Error: seleccioná una opción de la lista.")


def pedir_detalle(tipo):  # pide los datos extra según el tipo de evento
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


@requiere_permiso(1)
def registrar_evento_service():  # registra un evento logístico; opción 1 del menú de trazabilidad
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
            advertencias = validar_evento_permitido(  # controla que el evento tenga sentido para el estado actual
                envio[5], tipo, tipos_registrados(id_envio)
            )
        except ValueError as error:
            print(f"\nNo se puede registrar el evento: {mensaje_error(error)}")
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
            f"\n¿Registrar el evento «{formato.evento(tipo)}» para el envío "
            f"{id_envio}? (S/N): "
        ).strip().upper()

        if confirmacion != "S":
            print("Registro cancelado.")
            return

        usuario = obtener_sesion_actual()

        documento = {  # documento del evento para MongoDB
            "envio_id": id_envio,
            "tipo": tipo,
            "fecha_hora": fecha_hora,
            "ubicacion": ubicacion,
            "descripcion": descripcion,
            "usuario_id": usuario["id_usuario"] if usuario else None,
            "detalle": detalle,
            "fecha_registro": datetime.now(timezone.utc)
        }

        nuevo_estado = estado_nuevo_por_evento(tipo, envio[5])  # algunos eventos cambian el estado del envío

        if not nuevo_estado:
            # Sin cambio de estado: solo se guarda el evento en MongoDB, como siempre.
            id_evento = insertar_evento(documento)
            logger.info(
                "Evento %s registrado para el envío %s (id %s)",
                tipo, id_envio, id_evento
            )
            print("\nEvento registrado correctamente.")
            return

        # La fecha real de entrega es la del evento ENTREGADO.
        fecha_entrega = fecha_hora if tipo == "ENTREGADO" else None
        try:
            id_evento = registrar_evento_y_estado(  # guarda el evento en MongoDB y el estado en PostgreSQL juntos, o nada
                documento, id_envio, nuevo_estado, fecha_entrega
            )
        except Exception as error:
            logger.error("No se registró el evento %s del envío %s: %s",
                         tipo, id_envio, error)
            print(f"\nNo se registró el evento: {mensaje_error(error)}")  # no queda nada guardado ni pendiente
            return

        logger.info(
            "Evento %s registrado para el envío %s (id %s)",
            tipo, id_envio, id_evento
        )
        print("\nEvento registrado correctamente.")
        if fecha_entrega is not None:
            print(
                "Fecha real de entrega registrada: "
                f"{formatear_fecha(fecha_entrega)}"
            )
        print(f"Estado del envío actualizado a: {nuevo_estado}")
        sincronizar_envio_neo4j(id_envio)  # copia el estado nuevo a Neo4j (si falla, queda pendiente)

    except Exception as error:
        logger.exception("Error al registrar evento: %s", error)
        print(f"\nError al registrar el evento: {mensaje_error(error)}")

    finally:
        pausar()


# ------------------------------------------------------------------
# 2. Historial completo de un envío (MongoDB)
# ------------------------------------------------------------------

@requiere_permiso(1, portal=("CLIENTE",), portal_con_dato=True)
def historial_envio_service(envio=None):  # todos los eventos de un envío; opción 2 de trazabilidad y el portal del cliente
    """envio: fila ya verificada (portal del cliente); si falta, se pide."""
    print("\n--- HISTORIAL DE EVENTOS DE UN ENVÍO ---")

    try:
        envio = envio or pedir_envio()

        if envio is None:
            return

        eventos = listar_eventos_envio(envio[0])  # eventos de MongoDB en orden de fecha

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
        print(f"\nError al consultar el historial: {mensaje_error(error)}")

    finally:
        pausar()


# ------------------------------------------------------------------
# 3. Seguimiento temporal (PostgreSQL + MongoDB)
# ------------------------------------------------------------------

@requiere_permiso(1, portal=("CLIENTE",), portal_con_dato=True)
def seguimiento_temporal_service(envio=None):  # plazos y línea de tiempo de un envío; opción 3 de trazabilidad y el portal del cliente
    """envio: fila ya verificada (portal del cliente); si falta, se pide."""
    print("\n--- SEGUIMIENTO TEMPORAL DE UN ENVÍO ---")

    try:
        envio = envio or pedir_envio()

        if envio is None:
            return

        ahora = datetime.now(timezone.utc)
        eventos = listar_eventos_envio(envio[0])
        tramos = listar_tramos_de_envio(envio[0])  # tramos de PostgreSQL para la llegada estimada
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

            if llegada and normalizar(estado) not in ("entregado", "cancelado"):  # demorado si ya pasó la llegada estimada
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

        for evento in eventos:  # línea de tiempo con el tiempo entre eventos
            fecha = evento["fecha_hora"]
            ubicacion = (evento.get("ubicacion") or {}).get("nombre", "-")
            salto = ""

            if anterior is not None:
                salto = f"  (+{formatear_duracion(fecha - anterior)})"

            print(
                f"  {formatear_fecha(fecha)}  {formato.evento(evento['tipo']):<15} "
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
        print(f"\nError en el seguimiento temporal: {mensaje_error(error)}")

    finally:
        pausar()


# ------------------------------------------------------------------
# 4. Ruta completa de un envío (Neo4j)
# ------------------------------------------------------------------

@requiere_permiso(1, portal=("CLIENTE",), portal_con_dato=True)
def ruta_completa_service(envio=None):  # recorrido de un envío desde Neo4j; opción 4 de trazabilidad y el portal del cliente
    """envio: fila ya verificada (portal del cliente); si falta, se pide."""
    print("\n--- RUTA COMPLETA DE UN ENVÍO ---")

    try:
        envio = envio or pedir_envio()

        if envio is None:
            return

        filas = obtener_ruta_envio(envio[0])  # una fila por tramo desde el grafo

        if not filas:
            print(
                "\nEl envío no está en el grafo. Usá la opción "
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
                f"   Salida: {formato.fecha_tramo(fila['salida'])} | "
                f"Llegada estimada: {formato.fecha_tramo(fila['llegada'])}"
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
        print(f"\nError al consultar la ruta: {mensaje_error(error)}")

    finally:
        pausar()


# ------------------------------------------------------------------
# 5. Recorrido de un contenedor (PostgreSQL + MongoDB + Cassandra)
# ------------------------------------------------------------------

def pedir_cantidad_meses():  # cuántos meses de GPS mirar; la usa el recorrido de un contenedor
    while True:
        texto = input(
            "Meses hacia atrás a consultar (1-12, Enter = 3): "
        ).strip()

        if not texto:
            return 3

        if texto.isdigit() and 1 <= int(texto) <= 12:
            return int(texto)

        print("Error: ingresá un número entre 1 y 12.")


@requiere_permiso(1)
def recorrido_contenedor_service():  # eventos y posiciones GPS de un contenedor en una sola línea de tiempo; opción 5 de trazabilidad
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

        envios = listar_envios_de_contenedor(id_contenedor)  # envíos del contenedor (PostgreSQL)

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

        eventos = listar_eventos_envios([e[0] for e in envios])  # eventos de esos envíos (MongoDB)
        puntos = consultar_gps_contenedor(id_contenedor, meses)  # posiciones GPS por mes (Cassandra)

        linea = fusionar_recorrido(eventos, puntos)  # junta todo ordenado por fecha

        if not linea:
            print(
                "\nNo hay eventos ni posiciones GPS para ese período."
            )
            return

        gps = [item for item in linea if item["origen"] == "GPS"]  # de los GPS se muestra solo una muestra
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
                f"{'Evento' if item['origen'] == 'EVENTO' else 'GPS':<6} {item['texto']}"
            )

    except Exception as error:
        logger.exception("Error al reconstruir recorrido: %s", error)
        print(f"\nError al reconstruir el recorrido: {mensaje_error(error)}")

    finally:
        pausar()


# ------------------------------------------------------------------
# 6. Sincronizar o reparar la proyección (PostgreSQL -> Neo4j)
# ------------------------------------------------------------------

@requiere_permiso(1)
def sincronizar_proyeccion_service():  # pendientes y resincronización con Neo4j; opción 6 del menú de trazabilidad
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
            resueltos, fallidos = reparar_pendientes()  # reintenta los pendientes guardados en MongoDB
            print(f"\nResueltos: {resueltos} | Fallidos: {len(fallidos)}")

            for id_envio, error in fallidos:
                print(f"  Envío {id_envio}: {error}")

        elif opcion == "2":
            id_envio = pedir(
                "ID del envío: ",
                validar_entero_positivo_logistica,
                "El ID del envío"
            )
            if buscar_envio_por_id(id_envio) is None:
                print(f"\nNo existe el envío {id_envio}.")
            else:
                motivo = resincronizar_envio(id_envio)
                if motivo is None:
                    print(f"\nEnvío {id_envio} sincronizado correctamente.")
                else:
                    print(f"\nEl envío {id_envio} no se pudo sincronizar: {motivo}")
                    print("Quedó pendiente; podés reintentarlo con la opción 1.")

        elif opcion == "3":
            correctos, errores = resincronizar_todos()  # reconstruye todo el grafo desde PostgreSQL
            print(
                f"\nSincronizados: {correctos} | Con error: {len(errores)}"
            )

            for id_envio, error in errores:
                print(f"  Envío {id_envio}: {error}")

        elif opcion == "4":
            ok, fallos = 0, 0
            for pendiente in listar_pendientes_estado():  # aplica en PostgreSQL los cambios de estado que quedaron colgados
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
        print(f"\nError al sincronizar: {mensaje_error(error)}")

    finally:
        pausar()


# ------------------------------------------------------------------
# 7 y 8. Operadores en la red (Neo4j)
# ------------------------------------------------------------------

def fecha_entrega_de_pendiente(pendiente):  # fecha de entrega de un estado pendiente; la usa la opción 6 (cambios de estado)

    #Usa la guardada en el pendiente; si es un pendiente anterior que no la tiene, la toma del evento ENTREGADO original en MongoDB.
    
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


def cliente_visible(sesion):  # a qué cliente se limitan los datos según el usuario; la usan las opciones 7 y 8 y el portal

    # Depende de la PARTE del usuario, no de su nivel de permisos:
    # Usuario de un cliente: solo los datos de su cliente.
    # Usuario de proveedor u operador: no accede a datos de clientes.
    # Usuario interno (sin parte): todos.
    

    if sesion is None:
        raise PermissionError("Debés iniciar sesión.")

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


@requiere_permiso(1, portal=("CLIENTE",))
def quien_llevo_contenedor_service():  # operadores que llevaron un contenedor; opción 7 de trazabilidad y el portal del cliente
    print("\n--- ¿QUIÉN LLEVÓ EL CONTENEDOR? ---")

    try:
        restringido = cliente_visible(obtener_sesion_actual())  # un cliente solo ve sus propios envíos

        from app.repositories.contenedor_repository import buscar_contenedor_por_codigo

        codigo = input("Código del contenedor (ej. TDSU1000130): ").strip().upper()
        contenedor = buscar_contenedor_por_codigo(codigo) if codigo else None
        if contenedor is None:
            print("\nNo existe un contenedor con ese código.")
            return

        filas = operadores_de_contenedor(contenedor[0], restringido)  # consulta en Neo4j

        if not filas:
            if restringido:
                print("\nEse contenedor no tiene tramos en tus envíos.")
            else:
                print("\nNo hay tramos para ese contenedor. Si los datos son nuevos, "
                      "sincronice la red de rutas (opción 6).")
            return

        for fila in filas:
            print(
                f"Envío {fila['id_envio']} ({fila['cliente']}) | "
                f"Tramo {fila['id_tramo']} | {fila['medio']} | "
                f"{fila['origen']} -> {fila['destino']} | "
                f"Salida {formato.fecha(fila['salida'])} | "
                f"Operador: {fila['operador'] or 'sin asignar'}"
            )

    except PermissionError as error:
        print(f"\n{mensaje_error(error)}")
    except Exception as error:
        logger.exception("Error al consultar operadores del contenedor")
        print(f"\nError al consultar la red de operadores: {mensaje_error(error)}")

    finally:
        pausar()


@requiere_permiso(1)
def red_operadores_cliente_service():  # operadores de un cliente y con cuántos otros clientes los comparte; opción 8 de trazabilidad
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

        filas = red_operadores_cliente(id_cliente)  # consulta en Neo4j; de otros clientes solo la cantidad

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
        print(f"\n{mensaje_error(error)}")
    except Exception as error:
        logger.exception("Error al consultar la red del cliente")
        print(f"\nError al consultar la red de operadores: {mensaje_error(error)}")

    finally:
        pausar()
