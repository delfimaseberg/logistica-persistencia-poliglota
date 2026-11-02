"""Simular la falla de un sensor (requisito 4: un sensor que mide mal)."""

from datetime import datetime, timedelta, timezone

from app.repositories.lectura_iot_repository import registrar_lectura_db
from app.repositories.regla_alerta_repository import reglas_vigentes, umbral
from app.services.monitoreo_avanzado_service import sensores_activos
from app.utils.errores import mensaje_error
from app.services.autenticacion import requiere_permiso


FALLAS = {
    "1": ("Valor imposible", "imposible"),
    "2": ("Lecturas congeladas (siempre el mismo valor)", "congelada"),
    "3": ("Salto brusco de temperatura", "salto"),
}


def pausar():
    input("\nPresioná Enter para continuar...")


def lecturas_de_falla(falla, tipo_sensor, ahora, congeladas=6, salto_maximo=10.0):
    """[(fecha_hora, valores)] que reproducen la falla. Sin escribir nada."""
    tipo = str(tipo_sensor).strip().lower()
    campo = "humedad" if tipo == "humedad" else "temperatura"
    if falla == "imposible":
        if tipo == "humedad":
            return [(ahora, {"humedad": 140.0, "bateria": 80.0})]
        if tipo == "temperatura":
            return [(ahora, {"temperatura": -99.0, "bateria": 80.0})]
        return [(ahora, {"bateria": 150.0})]
    if falla == "congelada":
        if tipo not in ("temperatura", "humedad"):
            raise ValueError("Elegí un sensor de temperatura o de humedad.")
        valor = 5.5 if campo == "temperatura" else 60.0
        cantidad = int(congeladas)
        return [(ahora - timedelta(minutes=5 * (cantidad - 1 - i)),
                 {campo: valor, "bateria": 80.0}) for i in range(cantidad)]
    if falla == "salto":
        if tipo != "temperatura":
            raise ValueError("Elegí un sensor de temperatura.")
        return [(ahora - timedelta(minutes=10), {"temperatura": 4.0, "bateria": 80.0}),
                (ahora, {"temperatura": round(4.0 + salto_maximo + 5, 1), "bateria": 80.0})]
    raise ValueError("Falla desconocida.")


@requiere_permiso(1)
def simular_falla_sensor_service():
    print("\n--- SIMULAR FALLA DE SENSOR ---")
    try:
        sensores = sensores_activos()
        if not sensores:
            print("No hay sensores activos.")
            return
        for numero, sensor in enumerate(sensores, 1):
            print(f"  {numero}. Sensor {sensor[0]} | {sensor[3]} | contenedor {sensor[2]}")
        valor = input("Sensor (0 = cancelar): ").strip()
        if not valor.isdigit() or not 1 <= int(valor) <= len(sensores):
            print("Cancelado.")
            return
        sensor = sensores[int(valor) - 1]
        for clave, (texto, _) in FALLAS.items():
            print(f"  {clave}. {texto}")
        eleccion = FALLAS.get(input("Falla: ").strip())
        if eleccion is None:
            print("Opción inválida.")
            return
        vigentes = reglas_vigentes()
        lecturas = lecturas_de_falla(
            eleccion[1], sensor[3], datetime.now(timezone.utc),
            umbral(vigentes, "lecturas_congeladas", "MAX", 6),
            umbral(vigentes, "salto_temperatura", "MAX", 10.0))
        for fecha, valores in lecturas:
            registrar_lectura_db(sensor[0], sensor[1], fecha_hora=fecha, **valores)
        print(f"Se registraron {len(lecturas)} lectura(s) con la falla.")
        if input("¿Ejecutar la detección ahora? (S/N): ").strip().upper() == "S":
            from app.services.incidentes_service import revisar_lecturas_sensores
            resumen = revisar_lecturas_sensores()
            for id_sensor, tipo, descripcion, _ in resumen["detalle"]:
                if id_sensor == sensor[0]:
                    print(f"  {tipo}: {descripcion}")
            print(f"Alertas nuevas: {resumen['alertas_nuevas']} "
                  f"(mensajes enviados: {resumen['mensajes']})")
    except ValueError as error:
        print(f"No se simuló: {mensaje_error(error)}")
    except Exception as error:
        print(f"Error: {mensaje_error(error)}")
    finally:
        pausar()
