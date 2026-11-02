"""Administración interactiva de reglas y tarifas por envío."""

from datetime import date
from decimal import Decimal, InvalidOperation

from app.repositories import tarifas_repository as repo
from app.services import tarifas_service as service
from app.services.autenticacion import obtener_sesion_actual, verificar_permiso
from app.utils import formato
from app.utils.errores import mensaje_error


CRITERIOS = {
    "BASE": ("ENVIO", ("FIJO",)),
    "PESO": ("ENVIO", ("POR_KG",)),
    "DISTANCIA": ("ENVIO", ("POR_KM",)),
    "PESO_DISTANCIA": ("ENVIO", ("POR_KG_KM",)),
    "CATEGORIA": ("PARTIDA", ("FIJO", "POR_KG")),
    "FRAGIL": ("PARTIDA", ("FIJO", "POR_KG")),
    "TRANSPORTE": ("TRAMO", ("FIJO", "POR_KM")),
}


def _entero(mensaje):
    while True:
        valor = input(mensaje).strip()
        if valor.isdigit() and int(valor) > 0:
            return int(valor)
        print("Ingresá un entero positivo.")


def _importe(mensaje):
    while True:
        try:
            valor = Decimal(input(mensaje).strip().replace(",", "."))
            if valor.is_finite() and valor >= 0:
                return valor
        except (InvalidOperation, ValueError):
            pass
        print("Ingresá un importe decimal válido no negativo.")


def _fecha(mensaje, opcional=False):
    while True:
        valor = input(mensaje).strip()
        if opcional and not valor:
            return None
        try:
            return date.fromisoformat(valor)
        except ValueError:
            print("Usá el formato AAAA-MM-DD.")


def _usuario_id():
    usuario = obtener_sesion_actual()
    if not usuario:
        raise ValueError("La sesión expiró; volvé a iniciar sesión.")
    return usuario["id_usuario"]


def _listar_reglas():
    filas = repo.listar_reglas()
    if not filas:
        print("No hay reglas tarifarias registradas.")
        return
    print("\nN.º | Regla | Versión | Moneda | Vigencia | Estado")
    for r in filas:
        nombre = "Tarifa estándar" if r[1] == "TARIFA_ESTANDAR" else r[1]
        print(f"{r[0]} | {nombre} | {r[2]} | {r[3]} | desde {formato.fecha(r[4])}"
              f"{' hasta ' + formato.fecha(r[5]) if r[5] else ', sin fecha de fin'} | {str(r[6]).capitalize()}")
        detalle = repo.obtener_regla(r[0])
        for componente in detalle["componentes"]:
            print("   - {} {} | {} | importe {}".format(
                str(componente["criterio"]).replace("_", " ").capitalize(),
                componente["selector"] or "",
                str(componente["base_calculo"]).replace("_", " ").lower(),
                formato.dinero(componente["importe"]),
            ))


def _crear_categoria():
    codigo = input("Código de categoría definido por la empresa: ").strip()
    descripcion = input("Descripción: ").strip()
    service.registrar_tipo_carga(codigo, descripcion)
    print("Categoría registrada.")


def _registrar_carga():
    tipos = repo.listar_tipos_carga()
    if not tipos:
        print("Primero registrá una categoría de carga.")
        return
    envios = repo.listar_envios_tarifables()
    if not envios:
        print("No hay envíos disponibles.")
        return
    for e in envios:
        print(f"Envío {e[0]} | {e[2]} → {e[3]} | {e[4]}")
    ids = {e[0] for e in envios}
    while True:
        id_envio = _entero("N.º de envío: ")
        if id_envio in ids:
            break
        print("Elegí uno de los envíos de la lista.")
    for i, t in enumerate(tipos, 1):
        print(f"{i}. {t[1]}")
    while True:
        numero = _entero("Número de categoría: ")
        if numero <= len(tipos):
            break
        print(f"Elegí un número entre 1 y {len(tipos)}.")
    tipo = tipos[numero - 1]
    peso = _importe("Peso real de esta partida en kg: ")
    if peso <= 0:
        raise ValueError("El peso real debe ser mayor a cero.")
    fragil = input("¿Es frágil? (S/N): ").strip().upper()
    if fragil not in {"S", "N"}:
        raise ValueError("Indicá S o N para fragilidad.")
    descripcion = input("Descripción opcional: ").strip() or None
    service.registrar_partida_carga(id_envio, tipo[0], peso, fragil == "S", descripcion)
    print("Partida de carga registrada.")


def _registrar_distancia():
    id_tramo = _entero("ID del tramo: ")
    distancia = _importe("Distancia documentada del tramo en km: ")
    if distancia <= 0:
        raise ValueError("La distancia debe ser mayor a cero.")
    service.registrar_distancia_tramo(id_tramo, distancia)
    print("Distancia registrada; no fue inferida de las ubicaciones.")


def _crear_regla():
    codigo = input("Código identificador de la regla: ").strip()
    version = _entero("Número de versión: ")
    moneda = input("Código de moneda (configurado por la empresa): ").strip()
    desde = _fecha("Vigente desde (AAAA-MM-DD): ")
    hasta = _fecha("Vigente hasta (Enter si no vence): ", opcional=True)
    componentes = []
    while True:
        print("Criterios:", ", ".join(CRITERIOS))
        criterio = input("Criterio (0 para terminar): ").strip().upper()
        if criterio == "0":
            break
        if criterio not in CRITERIOS:
            print("Criterio no reconocido.")
            continue
        ambito, bases = CRITERIOS[criterio]
        print("Bases admitidas:", ", ".join(bases))
        base = input("Base de cálculo: ").strip().upper()
        if base not in bases:
            print("Base no admitida para ese criterio.")
            continue
        selector = None
        if criterio == "CATEGORIA":
            tipos = repo.listar_tipos_carga()
            for i, tipo in enumerate(tipos, 1):
                print(f"{i}. {tipo[0]} — {tipo[1]}")
            if not tipos:
                raise ValueError("Primero deben registrarse categorías de carga.")
            selector = tipos[_entero("Número de categoría: ") - 1][0]
        elif criterio == "TRANSPORTE":
            tipos = repo.listar_tipos_transporte()
            for i, tipo in enumerate(tipos, 1):
                print(f"{i}. {tipo}")
            if not tipos:
                raise ValueError("Primero debe existir un tipo de vehículo configurado.")
            selector = tipos[_entero("Número de medio de transporte: ") - 1]
        elif criterio == "FRAGIL":
            selector = "true"
        componentes.append({
            "criterio": criterio, "selector": selector,
            "ambito": ambito, "base_calculo": base,
            "importe": _importe("Importe configurado por la empresa: "),
        })
    id_regla = service.crear_regla(
        codigo, version, moneda, desde, hasta, _usuario_id(), componentes
    )
    print(f"Borrador de regla creado. ID: {id_regla}")


def _aprobar_regla():
    _listar_reglas()
    id_regla = _entero("ID de la regla a aprobar: ")
    referencia = input("Referencia documentada de aprobación: ").strip()
    service.aprobar_regla(id_regla, _usuario_id(), referencia)
    print("Regla aprobada. La versión anterior del mismo código queda reemplazada.")


def mostrar_menu_tarifas():
    if not verificar_permiso(3):
        return
    acciones = {
        "1": _crear_categoria,
        "2": _registrar_carga,
        "3": _registrar_distancia,
        "4": _crear_regla,
        "5": _listar_reglas,
        "6": _aprobar_regla,
        # 7-9 (tarifa borrador por envío y aprobación con perfil fiscal) ya
        # no forman parte del flujo: la factura por envío usa la tarifa
        # estándar (menú de facturación, opción "Precios de transporte").
    }
    while True:
        if not verificar_permiso(3):
            return
        print("\n--- REGLAS TARIFARIAS Y DATOS DE CARGA (avanzado) ---")
        print("1. Registrar categoría de carga")
        print("2. Registrar partida (categoría, peso real y fragilidad)")
        print("3. Registrar distancia documentada de tramo")
        print("4. Crear borrador de regla versionada")
        print("5. Consultar reglas")
        print("6. Aprobar regla")
        print("(Los precios que se facturan se definen en Facturación >")
        print(" 'Precios de transporte'.)")
        print("0. Volver")
        opcion = input("Opción: ").strip()
        if opcion == "0":
            return
        try:
            accion = acciones.get(opcion)
            if accion is None:
                print("Opción inválida.")
            else:
                accion()
        except Exception as error:
            print(f"No se completó la operación: {mensaje_error(error)}")
