"""Pantallas de alertas climáticas (fuente del riesgo climático, requisito 29)."""

from datetime import date, timedelta

from app.repositories import alerta_climatica_repository as repo
from app.services.autenticacion import obtener_sesion_actual, solo_internos
from app.utils.errores import mensaje_error
from app.services.autenticacion import requiere_permiso


def pausar():
    input("\nPresioná Enter para continuar...")


def _fecha(texto):  # AAAA-MM-DD a dd/mm/aaaa
    return date.fromisoformat(texto).strftime("%d/%m/%Y")


def describir(alerta):  # una alerta climática en una línea; la usan listar y anular
    estado = "" if alerta.get("estado") == "Vigente" else f" [{alerta.get('estado')}]"
    return (f"{alerta['fenomeno']} en {alerta['ubicacion']} | {alerta['severidad']} | "
            f"del {_fecha(alerta['fecha_desde'])} al {_fecha(alerta['fecha_hasta'])}{estado}")


def _pedir_fecha(mensaje, por_defecto):  # pide una fecha con valor por defecto; la usa registrar
    while True:
        texto = input(f"{mensaje} AAAA-MM-DD [Enter = {por_defecto:%d/%m/%Y}]: ").strip()
        if not texto:
            return por_defecto
        try:
            return date.fromisoformat(texto)
        except ValueError:
            print("Formato inválido.")


@solo_internos
def registrar_alerta_climatica_service():  # carga una alerta climática; opción 1 del menú de alertas climáticas
    print("\n--- REGISTRAR ALERTA CLIMÁTICA ---")
    print("La ubicación puede ser una ciudad (la de un tramo o del envío) o un país.")
    try:
        ubicacion = input("Ubicación: ").strip()
        fenomeno = input("Fenómeno (ej. Tormenta, Nevada, Niebla): ").strip()
        opciones = {str(i): s for i, s in enumerate(repo.SEVERIDADES_CLIMA, 1)}
        print("Severidad: " + " | ".join(f"{k}. {v}" for k, v in opciones.items()))
        severidad = opciones.get(input("Opción: ").strip())
        if severidad is None:
            print("Severidad inválida.")
            return
        hoy = date.today()
        desde = _pedir_fecha("Desde", hoy)
        hasta = _pedir_fecha("Hasta", desde + timedelta(days=2))  # por defecto dura tres días
        descripcion = input("Descripción (opcional): ").strip()
        repo.registrar_alerta_climatica(ubicacion, fenomeno, severidad, desde, hasta,  # se guarda en MongoDB
                                        obtener_sesion_actual()["id_usuario"], descripcion)
        print("Alerta climática registrada. Se considera en las próximas predicciones.")
    except ValueError as error:
        print(f"No se registró: {mensaje_error(error)}")
    except Exception as error:
        print(f"Error: {mensaje_error(error)}")
    finally:
        pausar()


def listar_alertas_climaticas_service():  # alertas vigentes; opción 2 del menú de alertas climáticas
    print("\n--- ALERTAS CLIMÁTICAS VIGENTES ---")
    try:
        alertas = repo.listar_alertas_climaticas()
        if not alertas:
            print("No hay alertas climáticas vigentes.")
        for numero, alerta in enumerate(alertas, 1):
            print(f"  {numero}. {describir(alerta)}")
            if alerta.get("descripcion"):
                print(f"     {alerta['descripcion']}")
    except Exception as error:
        print(f"Error: {mensaje_error(error)}")
    finally:
        pausar()


@solo_internos
def anular_alerta_climatica_service():  # anula una alerta (no la borra); opción 3 del menú de alertas climáticas
    print("\n--- ANULAR ALERTA CLIMÁTICA ---")
    try:
        alertas = repo.listar_alertas_climaticas()
        if not alertas:
            print("No hay alertas climáticas vigentes.")
            return
        for numero, alerta in enumerate(alertas, 1):
            print(f"  {numero}. {describir(alerta)}")
        valor = input("Número (0 = cancelar): ").strip()
        if not valor.isdigit() or not 1 <= int(valor) <= len(alertas):
            print("Cancelado.")
            return
        alerta = alertas[int(valor) - 1]
        if input("¿Confirmás la anulación? (S/N): ").strip().upper() != "S":
            print("Cancelado.")
            return
        if repo.anular_alerta_climatica(alerta["_id"], obtener_sesion_actual()["id_usuario"]):
            print("Alerta climática anulada (queda en el historial).")
        else:
            print("No se pudo anular.")
    except Exception as error:
        print(f"Error: {mensaje_error(error)}")
    finally:
        pausar()


OPCIONES_CLIMA = {  # opciones del menú de alertas climáticas
    "1": ("Registrar alerta climática", registrar_alerta_climatica_service),
    "2": ("Listar alertas climáticas vigentes", listar_alertas_climaticas_service),
    "3": ("Anular alerta climática", anular_alerta_climatica_service),
}


@requiere_permiso(3)
def menu_alertas_climaticas():  # menú de alertas climáticas; opción 7 del menú de predicciones
    while True:
        print("\n--- ALERTAS CLIMÁTICAS ---")
        for clave, (texto, _) in OPCIONES_CLIMA.items():
            print(f"{clave}. {texto}")
        print("0. Volver")
        opcion = input("Opción: ").strip()
        if opcion == "0":
            return
        if opcion in OPCIONES_CLIMA:
            OPCIONES_CLIMA[opcion][1]()
        else:
            print("Opción inválida.")
