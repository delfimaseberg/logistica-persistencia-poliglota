"""ABM de reglas de alerta (punto 9): umbrales que usa la detección."""

from app.repositories import regla_alerta_repository as repo
from app.services.autenticacion import obtener_sesion_actual, solo_internos
from app.utils import formato
from app.utils.errores import mensaje_error
from app.services.autenticacion import requiere_permiso


def pausar():
    input("\nPresioná Enter para continuar...")


def describir(regla):
    nombre, unidad = repo.VARIABLES[regla["variable"]][:2]
    signo = "menor a" if regla["limite"] == "MIN" else "mayor a"
    if regla["variable"] == "lecturas_congeladas":
        condicion = f"{int(regla['valor'])} lecturas idénticas seguidas"
    elif regla["variable"] == "horas_sin_transmision":
        condicion = f"más de {formato.compacto(regla['valor'])} h sin transmitir"
    elif regla["variable"] == "salto_temperatura":
        condicion = f"salto de más de {formato.compacto(regla['valor'])} °C en menos de 60 min"
    else:
        condicion = f"{nombre} {signo} {formato.compacto(regla['valor'])} {unidad}".rstrip()
    estado = "activa" if regla["activa"] else "inactiva"
    return f"{condicion} -> {regla['severidad']} ({estado})"


def _mostrar(reglas):
    if not reglas:
        print("No hay reglas.")
    for numero, regla in enumerate(reglas, 1):
        print(f"  {numero}. {describir(regla)}")


def _elegir(reglas):
    _mostrar(reglas)
    valor = input("Número de regla (0 = cancelar): ").strip()
    if valor.isdigit() and 1 <= int(valor) <= len(reglas):
        return reglas[int(valor) - 1]
    return None


def _pedir_severidad(actual=None):
    opciones = {str(i): s for i, s in enumerate(repo.SEVERIDADES, 1)}
    print("Severidad: " + " | ".join(f"{k}. {v}" for k, v in opciones.items()))
    texto = input("Opción" + (f" [Enter = {actual}]" if actual else "") + ": ").strip()
    if not texto and actual:
        return actual
    return opciones.get(texto)


def listar_reglas_service():
    print("\n--- REGLAS DE ALERTA ---")
    try:
        _mostrar(repo.listar_reglas())
        print("\nSi hay varias reglas para la misma variable se informa la más severa que se cumple.")
    except Exception as error:
        print(f"Error: {mensaje_error(error)}")
    finally:
        pausar()


@solo_internos
def crear_regla_service():
    print("\n--- NUEVA REGLA DE ALERTA ---")
    try:
        variables = list(repo.VARIABLES)
        for numero, variable in enumerate(variables, 1):
            nombre, unidad = repo.VARIABLES[variable][:2]
            print(f"  {numero}. {nombre}" + (f" ({unidad})" if unidad else ""))
        elegida = input("Variable (0 = cancelar): ").strip()
        if not elegida.isdigit() or not 1 <= int(elegida) <= len(variables):
            print("Cancelado.")
            return
        variable = variables[int(elegida) - 1]
        limites = repo.VARIABLES[variable][4]
        limite = limites[0]
        if len(limites) > 1:
            limite = "MIN" if input("Alerta si el valor es 1. menor | 2. mayor: ").strip() == "1" else "MAX"
        valor = input("Valor del umbral: ").strip()
        severidad = _pedir_severidad()
        if severidad is None:
            print("Severidad inválida.")
            return
        descripcion = input("Descripción (opcional): ").strip()
        repo.crear_regla(variable, limite, valor, severidad, descripcion,
                         obtener_sesion_actual()["id_usuario"])
        print("Regla creada. La detección la usa desde ahora.")
    except ValueError as error:
        print(f"No se creó la regla: {mensaje_error(error)}")
    except Exception as error:
        if "uq_regla_alerta_activa" in str(error):
            print("Ya hay una regla activa para esa variable, límite y severidad. Modifíquela.")
        else:
            print(f"Error: {mensaje_error(error)}")
    finally:
        pausar()


@solo_internos
def modificar_regla_service():
    print("\n--- MODIFICAR REGLA DE ALERTA ---")
    try:
        regla = _elegir(repo.listar_reglas())
        if regla is None:
            print("Cancelado.")
            return
        valor = input(f"Nuevo valor [Enter = {formato.compacto(regla['valor'])}]: ").strip() or regla["valor"]
        severidad = _pedir_severidad(regla["severidad"])
        if severidad is None:
            print("Severidad inválida.")
            return
        repo.modificar_regla(regla["id_regla"], valor, severidad,
                             obtener_sesion_actual()["id_usuario"])
        print("Regla modificada.")
    except ValueError as error:
        print(f"No se modificó: {mensaje_error(error)}")
    except Exception as error:
        if "uq_regla_alerta_activa" in str(error):
            print("Ya hay otra regla activa con esa variable, límite y severidad.")
        else:
            print(f"Error: {mensaje_error(error)}")
    finally:
        pausar()


@solo_internos
def cambiar_estado_regla_service():
    print("\n--- ACTIVAR O DESACTIVAR UNA REGLA ---")
    try:
        regla = _elegir(repo.listar_reglas())
        if regla is None:
            print("Cancelado.")
            return
        activar = not regla["activa"]
        if not activar and repo.contar_activas(regla["variable"], regla["limite"]) == 1:
            print("Atención: es la última regla activa de esa variable; "
                  "sin ella no se generan esas alertas.")
        accion = "activar" if activar else "desactivar"
        if input(f"¿Confirmás {accion} la regla? (S/N): ").strip().upper() != "S":
            print("Cancelado.")
            return
        if repo.cambiar_estado_regla(regla["id_regla"], activar,
                                     obtener_sesion_actual()["id_usuario"]):
            print("Regla " + ("activada." if activar else "desactivada."))
        else:
            print("No se pudo cambiar el estado.")
    except Exception as error:
        if "uq_regla_alerta_activa" in str(error):
            print("Ya hay otra regla activa con esa variable, límite y severidad.")
        else:
            print(f"Error: {mensaje_error(error)}")
    finally:
        pausar()


OPCIONES_REGLAS = {
    "1": ("Listar reglas", listar_reglas_service),
    "2": ("Crear regla", crear_regla_service),
    "3": ("Modificar valor o severidad", modificar_regla_service),
    "4": ("Activar o desactivar", cambiar_estado_regla_service),
}


@requiere_permiso(3)
def menu_reglas_alerta():
    while True:
        print("\n--- REGLAS DE ALERTA (UMBRALES) ---")
        for clave, (texto, _) in OPCIONES_REGLAS.items():
            print(f"{clave}. {texto}")
        print("0. Volver")
        opcion = input("Opción: ").strip()
        if opcion == "0":
            return
        if opcion in OPCIONES_REGLAS:
            OPCIONES_REGLAS[opcion][1]()
        else:
            print("Opción inválida.")
