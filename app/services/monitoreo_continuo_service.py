
import time
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

from app.services.monitoreo_avanzado_service import (
    sensores_activos,
    generar_valores_simulados
)
from app.repositories.lectura_iot_repository import (
    registrar_lectura_db,
    consultar_ultima_lectura_db
)


INTERVALO_SEGUNDOS = 10
HORAS_SIN_LECTURAS = 24
ZONA_ARGENTINA = ZoneInfo("America/Argentina/Buenos_Aires")


def controlar_sensores(sensores):
    limite = datetime.now(timezone.utc) - timedelta(
        hours=HORAS_SIN_LECTURAS
    )

    sin_lecturas = []
    atrasados = []
    errores = []

    for sensor in sensores:
        id_sensor = sensor[0]

        try:
            lectura = consultar_ultima_lectura_db(id_sensor)

            if lectura is None:
                sin_lecturas.append(id_sensor)
                continue

            fecha = lectura.fecha_hora

            if fecha.tzinfo is None:
                fecha = fecha.replace(tzinfo=timezone.utc)

            if fecha < limite:
                atrasados.append(id_sensor)

        except Exception as error:
            errores.append((id_sensor, str(error)))

    return sin_lecturas, atrasados, errores


def monitoreo_continuo_service():
    print("\n--- MONITOREO IoT CONTINUO ---")
    print(
        f"\nSe generarán lecturas simuladas cada "
        f"{INTERVALO_SEGUNDOS} segundos."
    )
    print(
        f"Se controlarán sensores sin lecturas "
        f"durante más de {HORAS_SIN_LECTURAS} horas."
    )
    print("\nPara detener el proceso, presioná Ctrl+C.")

    confirmacion = input(
        "\n¿Iniciar monitoreo automático? (S/N): "
    ).strip().upper()

    if confirmacion != "S":
        print("\nMonitoreo cancelado.")
        input("\nPresione Enter para continuar...")
        return

    rondas = 0
    total_lecturas = 0
    total_errores = 0

    print("\nMonitoreo iniciado.")

    try:
        while True:
            rondas += 1

            fecha_actual = datetime.now(
                ZONA_ARGENTINA
            ).strftime("%d/%m/%Y %H:%M:%S")

            print("\n" + "=" * 50)
            print(f"RONDA {rondas} | {fecha_actual}")
            print("=" * 50)

            try:
                sensores = sensores_activos()

            except Exception as error:
                total_errores += 1
                print(
                    f"\nError al consultar sensores: {error}"
                )
                print(
                    f"Nuevo intento en "
                    f"{INTERVALO_SEGUNDOS} segundos."
                )
                time.sleep(INTERVALO_SEGUNDOS)
                continue

            if not sensores:
                print("\nNo hay sensores activos.")

            else:
                print(
                    f"\nSensores activos: {len(sensores)}"
                )

                # Verificar lecturas anteriores antes
                # de generar las nuevas.
                sin_lecturas, atrasados, errores_control = (
                    controlar_sensores(sensores)
                )

                if sin_lecturas:
                    print(
                        "\nSensores sin lecturas: "
                        + ", ".join(map(str, sin_lecturas))
                    )

                if atrasados:
                    print(
                        "\nSensores con lecturas atrasadas: "
                        + ", ".join(map(str, atrasados))
                    )

                if not sin_lecturas and not atrasados:
                    print(
                        "\nTodos los sensores consultados "
                        "tienen lecturas recientes."
                    )

                for id_sensor, error in errores_control:
                    total_errores += 1
                    print(
                        f"Error al controlar el sensor "
                        f"{id_sensor}: {error}"
                    )

                print("\nRegistrando lecturas:")

                for sensor in sensores:
                    id_sensor = sensor[0]
                    id_contenedor = sensor[1]
                    tipo = sensor[3]

                    valores = generar_valores_simulados(tipo)

                    if valores is None:
                        print(
                            f"Sensor {id_sensor}: "
                            f"tipo no compatible ({tipo})."
                        )
                        continue

                    try:
                        id_lectura = registrar_lectura_db(
                            id_sensor=id_sensor,
                            id_contenedor=id_contenedor,
                            **valores
                        )

                        total_lecturas += 1

                        print(
                            f"Sensor {id_sensor} ({tipo}): "
                            f"lectura {id_lectura}"
                        )

                    except Exception as error:
                        total_errores += 1

                        print(
                            f"Error al registrar lectura "
                            f"del sensor {id_sensor}: {error}"
                        )

            print(
                f"\nLecturas registradas en total: "
                f"{total_lecturas}"
            )
            print(f"Errores acumulados: {total_errores}")
            print(
                f"Próxima ronda en "
                f"{INTERVALO_SEGUNDOS} segundos."
            )
            print("Presioná Ctrl+C para detener.")

            time.sleep(INTERVALO_SEGUNDOS)

    except KeyboardInterrupt:
        print("\n\nMonitoreo detenido por el usuario.")

    finally:
        print("\n--- RESUMEN ---")
        print(f"Rondas ejecutadas: {rondas}")
        print(f"Lecturas registradas: {total_lecturas}")
        print(f"Errores: {total_errores}")
        print(
            "\nLas lecturas permanecen guardadas "
            "en Cassandra."
        )

        input("\nPresione Enter para volver...")
