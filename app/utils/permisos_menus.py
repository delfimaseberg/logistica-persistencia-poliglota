"""Qué nivel exige cada menú interno para cada servicio que llama.

Se usa en los tests para comprobar que cada servicio verifique el permiso
por sí mismo (segunda barrera además del menú). No se usa en ejecución.
"""

import ast
import importlib
import inspect
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]  # carpeta raíz del proyecto

# Menú principal interno: módulo -> nivel de la opción (menu_principal.OPCIONES_INTERNAS).
MENUS_INTERNOS = {  # menú y nivel que pide para entrar
    "app.ui.menu_clientes": 1,
    "app.ui.menu_usuarios": 3,
    "app.ui.menu_roles": 5,
    "app.ui.menu_envios": 1,
    "app.ui.menu_contenedores": 1,
    "app.ui.menu_vehiculos": 1,
    "app.ui.menu_monitoreo": 1,
    "app.ui.menu_trazabilidad": 1,
    "app.ui.menu_incidentes": 1,
    "app.ui.menu_facturacion": 1,
    "app.ui.menu_tarifas": 3,
    "app.ui.menu_reportes": 1,
    "app.ui.menu_predicciones": 1,
    "app.ui.menu_proveedores": 3,
    "app.ui.menu_operadores": 3,
}


def _nivel_en(nodo):  # nivel de un verificar_permiso(N) en el código
    """N si el nodo es verificar_permiso(N) / ejecutar_*(f, N) / tupla (texto, f, N)."""
    if isinstance(nodo, ast.Call) and getattr(nodo.func, "id", "") == "verificar_permiso":
        if nodo.args and isinstance(nodo.args[0], ast.Constant):
            return nodo.args[0].value
    return None


def servicios_por_menu():  # nivel que exige cada menú para cada servicio que llama; la usan los tests de permisos
    """{(módulo del servicio, nombre): nivel mínimo que exige el menú}."""
    resultado = {}
    for modulo, nivel_menu in MENUS_INTERNOS.items():
        mod = importlib.import_module(modulo)
        arbol = ast.parse(inspect.getsource(mod))  # lee el código del menú, sin ejecutarlo
        nombres = {}
        for nombre, objeto in vars(mod).items():
            if inspect.isfunction(objeto) and objeto.__module__.startswith("app.services"):
                nombres[nombre] = objeto
            elif inspect.ismodule(objeto) and objeto.__name__.startswith("app.services"):
                nombres[nombre] = objeto

        def registrar(funcion, nivel):  # anota el nivel de un servicio
            original = inspect.unwrap(funcion)
            if original.__module__ == "app.services.autenticacion":
                return            # verificar_permiso / obtener_sesion_actual
            clave = (original.__module__, original.__name__)
            # Si dos menús la llaman con niveles distintos, vale el menor.
            resultado[clave] = min(resultado.get(clave, nivel), nivel)

        def visitar(nodo, nivel):  # recorre el código del menú buscando llamadas a servicios
            # Un if verificar_permiso(N) sube el nivel de su cuerpo.
            if isinstance(nodo, ast.If):
                n = _nivel_en(nodo.test)
                if n is not None:
                    for hijo in nodo.body:
                        visitar(hijo, max(nivel, n))
                    for hijo in nodo.orelse:
                        visitar(hijo, nivel)
                    return
            # (texto, funcion, nivel) en las tablas de opciones.
            if isinstance(nodo, ast.Tuple) and len(nodo.elts) == 3 and \
                    isinstance(nodo.elts[2], ast.Constant) and isinstance(nodo.elts[2].value, int):
                for f in _funciones(nodo.elts[1]):
                    registrar(f, max(nivel, nodo.elts[2].value))
                return
            # ejecutar_operacion(funcion, N)
            if isinstance(nodo, ast.Call) and len(nodo.args) == 2 and \
                    isinstance(nodo.args[1], ast.Constant) and isinstance(nodo.args[1].value, int):
                encontradas = list(_funciones(nodo.args[0]))
                for f in encontradas:
                    registrar(f, max(nivel, nodo.args[1].value))
                if encontradas:
                    return
            for f in _funciones(nodo):
                registrar(f, nivel)
            for hijo in ast.iter_child_nodes(nodo):
                visitar(hijo, nivel)

        def _funciones(nodo):  # servicios que aparecen en ese pedazo de código
            """Funciones de servicio referenciadas directamente por el nodo."""
            if isinstance(nodo, ast.Name) and inspect.isfunction(nombres.get(nodo.id)):
                yield nombres[nodo.id]
            elif isinstance(nodo, ast.Attribute) and isinstance(nodo.value, ast.Name) \
                    and inspect.ismodule(nombres.get(nodo.value.id)):
                objeto = getattr(nombres[nodo.value.id], nodo.attr, None)
                if inspect.isfunction(objeto):
                    yield objeto
            elif isinstance(nodo, ast.Lambda):
                for sub in ast.walk(nodo.body):
                    if sub is not nodo:
                        yield from _funciones_simple(sub)

        def _funciones_simple(nodo):
            if isinstance(nodo, (ast.Name, ast.Attribute)):
                yield from _funciones(nodo)

        # Nivel del menú: el del menú principal o el que exige la propia función del menú.
        for funcion in arbol.body:
            if not isinstance(funcion, ast.FunctionDef):
                continue
            nivel = nivel_menu
            # Barrera de entrada del menú: "if not verificar_permiso(N): return".
            primera = next((n for sub in funcion.body if isinstance(sub, ast.If)
                            for n in [_nivel_en(sub.test.operand) if isinstance(sub.test, ast.UnaryOp) else None]
                            if n is not None), None)
            if primera is not None:
                nivel = max(nivel, primera)
            for hijo in funcion.body:
                visitar(hijo, nivel)
        for nodo in arbol.body:
            if isinstance(nodo, ast.Assign):
                visitar(nodo, nivel_menu)
    return resultado
