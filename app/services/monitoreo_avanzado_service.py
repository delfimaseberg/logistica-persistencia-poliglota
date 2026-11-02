
from datetime import datetime, timezone, timedelta
from random import uniform
from zoneinfo import ZoneInfo
from urllib.parse import urlencode
import webbrowser

from app.repositories.sensor_repository import (
    listar_sensores,
    buscar_sensor_por_id,
    listar_sensores_por_contenedor,
)
from app.repositories.contenedor_repository import buscar_contenedor_por_id
from app.repositories.lectura_iot_repository import (
    registrar_lectura_db,
    consultar_ultima_lectura_db,
    consultar_lecturas_sensor_db
)
from app.utils.errores import mensaje_error
from app.utils import formato
from app.services.autenticacion import requiere_permiso


def pausar():
    input("\nPresioná Enter para continuar...")


def sensores_activos():
    return [
        sensor for sensor in listar_sensores()
        if str(sensor[6]).strip().lower() == "activo"
    ]


def generar_valores_simulados(tipo):
    tipo = str(tipo).strip().lower()

    valores = {
        "temperatura": None,
        "humedad": None,
        "vibracion": None,
        "gps_latitud": None,
        "gps_longitud": None,
        "bateria": round(uniform(30, 100), 2)
    }

    if tipo == "temperatura":
        valores["temperatura"] = round(uniform(2, 10), 2)

    elif tipo == "humedad":
        valores["humedad"] = round(uniform(40, 85), 2)

    elif tipo in ("vibracion", "vibración"):
        valores["vibracion"] = round(uniform(0, 20), 2)

    elif tipo == "gps":
        # Coordenadas ficticias cercanas a Buenos Aires.
        valores["gps_latitud"] = round(
            uniform(-34.65, -34.45), 6
        )
        valores["gps_longitud"] = round(
            uniform(-58.55, -58.35), 6
        )

    else:
        return None

    return valores


def describir_valores(valores):
    """'6,25 °C | batería 80,1 %' con formato argentino."""
    partes = []
    if valores.get("temperatura") is not None:
        partes.append(f"{formato.compacto(valores['temperatura'])} °C")
    if valores.get("humedad") is not None:
        partes.append(f"humedad {formato.compacto(valores['humedad'])} %")
    if valores.get("vibracion") is not None:
        partes.append(f"vibración {formato.compacto(valores['vibracion'])}")
    if valores.get("gps_latitud") is not None:
        partes.append(f"latitud {formato.compacto(valores['gps_latitud'], 5)} | "
                      f"longitud {formato.compacto(valores['gps_longitud'], 5)}")
    if valores.get("bateria") is not None:
        partes.append(f"batería {formato.compacto(valores['bateria'], 1)} %")
    return " | ".join(partes)


@requiere_permiso(1)
def simular_lecturas_service():
    print("\n--- SIMULAR LECTURAS IoT ---")

    try:
        sensores = sensores_activos()

        if not sensores:
            print("\nNo hay sensores activos.")
            return

        print(f"\nSensores activos: {len(sensores)}")
        print(
            "Se generarán lecturas ficticias para "
            "los sensores compatibles."
        )

        while True:
            try:
                cantidad = int(input(
                    "\nCantidad de rondas (1 a 20): "
                ).strip())

                if 1 <= cantidad <= 20:
                    break

                print("Ingresá un número entre 1 y 20.")

            except ValueError:
                print("Ingresá un número entero válido.")

        confirmacion = input(
            "\n¿Registrar estas lecturas? (S/N): "
        ).strip().upper()

        if confirmacion != "S":
            print("\nSimulación cancelada.")
            return

        total = 0
        omitidos = set()
        errores = []

        for ronda in range(1, cantidad + 1):
            print(f"\nRonda {ronda} de {cantidad}")

            for sensor in sensores:
                id_sensor = sensor[0]
                id_contenedor = sensor[1]
                tipo = sensor[3]

                valores = generar_valores_simulados(tipo)

                if valores is None:
                    omitidos.add(id_sensor)
                    continue

                try:
                    registrar_lectura_db(
                        id_sensor=id_sensor,
                        id_contenedor=id_contenedor,
                        **valores
                    )

                    total += 1

                    print(
                        f"Sensor {id_sensor} ({tipo}) | "
                        f"contenedor {sensor[2]}: {describir_valores(valores)}"
                    )

                except Exception as error:
                    errores.append(
                        f"Sensor {id_sensor}: {mensaje_error(error)}"
                    )

        print("\n--- RESULTADO DE LA SIMULACIÓN ---")
        print(f"Lecturas registradas: {total}")
        print(f"Sensores omitidos: {len(omitidos)}")
        print(f"Errores: {len(errores)}")

        if omitidos:
            print(
                "Sensores con tipo no compatible: "
                + ", ".join(map(str, sorted(omitidos)))
            )

        for error in errores:
            print(f"Error: {error}")

        print(
            "\nNota: son datos simulados, "
            "no mediciones de dispositivos reales."
        )

    except Exception as error:
        print(f"\nError en la simulación: {mensaje_error(error)}")

    finally:
        pausar()


@requiere_permiso(1)
def detectar_sensores_inactivos_service():
    print("\n--- DETECTAR SENSORES SIN LECTURAS RECIENTES ---")

    try:
        while True:
            try:
                horas = float(
                    input(
                        "Horas máximas sin transmitir "
                        "(ejemplo 24): "
                    ).strip().replace(",", ".")
                )

                if 0 < horas <= 8760:
                    break

                print(
                    "Ingresá un valor mayor que 0 "
                    "y menor o igual a 8760."
                )

            except ValueError:
                print("Ingresá una cantidad de horas válida.")

        sensores = sensores_activos()
        ahora = datetime.now(timezone.utc)
        limite = ahora - timedelta(hours=horas)

        sin_lecturas = []
        atrasados = []
        al_dia = []

        for sensor in sensores:
            id_sensor = sensor[0]
            lectura = consultar_ultima_lectura_db(id_sensor)

            if lectura is None:
                sin_lecturas.append(sensor)
                continue

            fecha = lectura.fecha_hora

            if fecha.tzinfo is None:
                fecha = fecha.replace(tzinfo=timezone.utc)

            if fecha < limite:
                atrasados.append((sensor, fecha))
            else:
                al_dia.append(sensor)

        print("\n--- RESULTADOS ---")
        print(f"Sensores activos: {len(sensores)}")
        print(f"Con lecturas recientes: {len(al_dia)}")
        print(f"Sin lecturas registradas: {len(sin_lecturas)}")
        print(f"Con lecturas atrasadas: {len(atrasados)}")

        if sin_lecturas:
            print("\nSENSORES SIN LECTURAS:")
            for sensor in sin_lecturas:
                print(
                    f"Sensor {sensor[0]} | "
                    f"Tipo: {sensor[3]} | "
                    f"Contenedor: {sensor[2]}"
                )

        if atrasados:
            print("\nSENSORES CON LECTURAS ATRASADAS:")
            zona = ZoneInfo("America/Argentina/Buenos_Aires")

            for sensor, fecha in atrasados:
                fecha_local = fecha.astimezone(zona)

                print(
                    f"Sensor {sensor[0]} | "
                    f"Contenedor: {sensor[2]} | "
                    f"Última lectura: "
                    f"{fecha_local.strftime('%d/%m/%Y %H:%M:%S')}"
                )

        print(
            "\nEsta consulta no cambia automáticamente "
            "el estado del sensor."
        )

    except Exception as error:
        print(f"\nError al detectar sensores inactivos: {mensaje_error(error)}")

    finally:
        pausar()


@requiere_permiso(1)
def consultar_posiciones_gps_service():
    print("\n--- CONSULTAR POSICIONES GPS ---")

    def pedir_id_positivo(mensaje):
        while True:
            try:
                valor = int(input(mensaje).strip())
                if valor > 0:
                    return valor
            except ValueError:
                pass
            print("Ingresá un ID positivo válido.")

    try:
        modo = input(
            "Consultar por: 1. Contenedor | 2. Sensor GPS: "
        ).strip()

        if modo not in {"1", "2"}:
            print("\nOpción inválida.")
            return

        if modo == "1":
            id_contenedor = pedir_id_positivo("ID del contenedor: ")
            contenedor = buscar_contenedor_por_id(id_contenedor)

            if contenedor is None:
                print("\nNo existe ese contenedor.")
                return

            sensores = listar_sensores_por_contenedor(id_contenedor)
            sensores_gps = [
                sensor for sensor in sensores
                if str(sensor[3]).strip().lower() == "gps"
            ]

            if not sensores_gps:
                print(
                    "\nEl contenedor no tiene un sensor GPS asociado; "
                    "no se puede consultar su ubicación."
                )
                return

            if len(sensores_gps) == 1:
                sensor = sensores_gps[0]
            else:
                print(
                    "\nEl contenedor tiene varios sensores GPS asociados. "
                    "Seleccioná explícitamente uno:"
                )
                for sensor_gps in sensores_gps:
                    print(f"  Sensor GPS ID: {sensor_gps[0]}")

                id_sensor = pedir_id_positivo("ID del sensor GPS: ")
                sensor = next(
                    (
                        item for item in sensores_gps
                        if item[0] == id_sensor
                    ),
                    None,
                )
                if sensor is None:
                    print(
                        "\nEl sensor seleccionado no es un sensor GPS "
                        "asociado a este contenedor."
                    )
                    return
        else:
            id_sensor = pedir_id_positivo("ID del sensor GPS: ")
            sensor = buscar_sensor_por_id(id_sensor)

            if sensor is None:
                print("\nEl sensor no existe.")
                return

            if str(sensor[3]).strip().lower() != "gps":
                print("\nEl sensor seleccionado no es de tipo GPS.")
                return

            contenedor = buscar_contenedor_por_id(sensor[1])
            if contenedor is None:
                print("\nEl contenedor asociado al sensor no existe.")
                return

        if str(sensor[3]).strip().lower() != "gps":
            print("\nEl sensor asociado no es de tipo GPS.")
            return

        print(f"\nContenedor ID: {contenedor[0]}")
        print(f"Código del contenedor: {contenedor[1]}")
        print(f"Sensor GPS asociado: {sensor[0]}")

        mes = input(
            "Mes (AAAA-MM, Enter = mes UTC actual): "
        ).strip()

        if not mes:
            mes = datetime.now(timezone.utc).strftime("%Y-%m")

        try:
            fecha_mes = datetime.strptime(mes, "%Y-%m")
            if fecha_mes.strftime("%Y-%m") != mes:
                raise ValueError
        except ValueError:
            print("\nMes inválido. Usá AAAA-MM.")
            return

        lecturas = consultar_lecturas_sensor_db(
            sensor[0], mes, limite=100
        )
        posiciones = [
            lectura for lectura in lecturas
            if lectura.gps_latitud is not None
            and lectura.gps_longitud is not None
        ]

        if not posiciones:
            print("\nNo hay posiciones GPS registradas para ese sensor.")
            return

        print(f"\nPosiciones encontradas: {len(posiciones)}")
        zona = ZoneInfo("America/Argentina/Buenos_Aires")

        for numero, lectura in enumerate(posiciones, 1):
            fecha = lectura.fecha_hora
            if fecha.tzinfo is None:
                fecha = fecha.replace(tzinfo=timezone.utc)
            fecha_local = fecha.astimezone(zona)

            print(
                f"{numero}. "
                f"{fecha_local.strftime('%d/%m/%Y %H:%M:%S')} | "
                f"Lat: {lectura.gps_latitud} | "
                f"Lon: {lectura.gps_longitud}"
            )

        print("\nPodés abrir una posición en Google Maps.")
        opcion = input(
            "Número de posición (Enter para volver): "
        ).strip()
        if not opcion:
            return

        try:
            indice = int(opcion)
            if not 1 <= indice <= len(posiciones):
                print("\nNúmero fuera de rango.")
                return
        except ValueError:
            print("\nNúmero inválido.")
            return

        posicion = posiciones[indice - 1]
        coordenadas = (
            f"{posicion.gps_latitud},{posicion.gps_longitud}"
        )
        url = (
            "https://www.google.com/maps/search/?"
            + urlencode({"api": "1", "query": coordenadas})
        )

        print(f"\nMapa: {url}")
        if webbrowser.open(url):
            print("Se solicitó abrir el mapa en el navegador.")
        else:
            print("Abrí el enlace manualmente.")

    except Exception as error:
        print(f"\nError al consultar posiciones GPS: {mensaje_error(error)}")

    finally:
        pausar()
