"""Casos de uso de reglas tarifarias y tarifas por envío."""

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from app.repositories import tarifas_repository as repo
from app.services.tarifas_calculo import validar_estructura_componentes
from app.utils.validaciones_datos import (
    DISTANCIA_MAXIMA_KM, PESO_MAXIMO_KG, controlar_cantidad, controlar_maximo,
)
from app.services.autenticacion import requiere_permiso


def _hoy_buenos_aires():
    return datetime.now(ZoneInfo("America/Argentina/Buenos_Aires")).date()


@requiere_permiso(3, lanzar=True)
def registrar_tipo_carga(codigo, descripcion):
    codigo = str(codigo or "").strip().upper()
    descripcion = str(descripcion or "").strip()
    if not codigo or len(codigo) > 40 or not descripcion or len(descripcion) > 150:
        raise ValueError("El código (hasta 40 caracteres) y la descripción (hasta 150) "
                         "de la categoría son obligatorios.")
    return repo.crear_tipo_carga(codigo, descripcion)


@requiere_permiso(3, lanzar=True)
def registrar_partida_carga(id_envio, tipo_carga, peso_kg, fragil, descripcion=None):
    try:
        peso = Decimal(str(peso_kg))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("El peso real debe ser un decimal válido en kg.")
    if not peso.is_finite() or peso <= 0:
        raise ValueError("El peso real debe ser mayor a cero.")
    if max(0, -peso.as_tuple().exponent) > 3:
        raise ValueError("El peso admite hasta tres decimales de kg.")
    controlar_cantidad(peso, "El peso de la partida", PESO_MAXIMO_KG, "kg")
    if not isinstance(fragil, bool):
        raise ValueError("La fragilidad debe indicarse explícitamente.")
    if descripcion and len(str(descripcion)) > 1000:
        raise ValueError("La descripción de la partida no puede superar 1000 caracteres.")
    return repo.agregar_carga(id_envio, tipo_carga, peso, fragil, descripcion)


@requiere_permiso(3, lanzar=True)
def registrar_distancia_tramo(id_tramo, distancia_km):
    try:
        distancia = Decimal(str(distancia_km))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("La distancia debe ser un decimal válido en km.")
    if not distancia.is_finite() or distancia <= 0:
        raise ValueError("La distancia debe ser mayor a cero.")
    if max(0, -distancia.as_tuple().exponent) > 3:
        raise ValueError("La distancia admite hasta tres decimales de km.")
    controlar_cantidad(distancia, "La distancia", DISTANCIA_MAXIMA_KM, "km")
    if not repo.actualizar_distancia_tramo(id_tramo, distancia):
        raise ValueError("No existe ese tramo.")


@requiere_permiso(3, lanzar=True)
def crear_regla(codigo, version, moneda, desde, hasta, usuario_id, componentes):
    codigo = str(codigo or "").strip().upper()
    moneda = str(moneda or "").strip().upper()
    if not codigo or len(codigo) > 60:
        raise ValueError("El código de regla es obligatorio (máximo 60 caracteres).")
    if len(moneda) != 3 or not moneda.isalpha():
        raise ValueError("La regla requiere un código de moneda configurado explícitamente.")
    if not isinstance(desde, date) or (hasta is not None and hasta < desde):
        raise ValueError("El período de vigencia de la regla no es válido.")
    if not usuario_id:
        raise ValueError("No hay un usuario autenticado para crear la regla.")
    if int(version) <= 0:
        raise ValueError("La versión debe ser un entero positivo.")
    validar_estructura_componentes(componentes)
    tipos = {str(row[0]).casefold() for row in repo.listar_tipos_carga()}
    medios = {str(valor).casefold() for valor in repo.listar_tipos_transporte()}
    for component in componentes:
        selector = str(component.get("selector") or "").strip().casefold()
        if component.get("criterio") == "CATEGORIA" and selector not in tipos:
            raise ValueError("El selector de categoría debe existir en las categorías configuradas.")
        if component.get("criterio") == "TRANSPORTE" and selector not in medios:
            raise ValueError("El selector de transporte debe corresponder a un tipo de vehículo configurado.")
        importe = Decimal(str(component["importe"]))
        if max(0, -importe.as_tuple().exponent) > 6:
            raise ValueError("Los componentes de regla admiten hasta seis decimales.")
        if not importe.is_finite() or importe < 0:
            raise ValueError("Los importes de la regla no pueden ser negativos.")
        controlar_maximo(importe, "El importe del componente")
    return repo.crear_regla(codigo, int(version), moneda, desde, hasta,
                            usuario_id, componentes)


@requiere_permiso(3, lanzar=True)
def aprobar_regla(id_regla, usuario_id, referencia):
    if not str(referencia or "").strip():
        raise ValueError("La aprobación requiere una referencia documentada.")
    regla = repo.obtener_regla(id_regla)
    if not regla or regla["estado"] != "BORRADOR":
        raise ValueError("La regla no existe o no está en borrador.")
    hoy = _hoy_buenos_aires()
    if regla["vigente_desde"] > hoy or (
        regla["vigente_hasta"] is not None and regla["vigente_hasta"] < hoy
    ):
        raise ValueError("En esta versión solo se pueden aprobar reglas vigentes hoy.")
    validar_estructura_componentes(regla["componentes"])
    return repo.aprobar_regla(id_regla, usuario_id, str(referencia).strip())


def reemplazar_tarifa_aprobada(id_tarifa, usuario_id, motivo):
    """Solicita el único cambio de estado autorizado para una tarifa aprobada."""
    if not usuario_id or not str(motivo or "").strip():
        raise ValueError("El reemplazo requiere usuario y motivo documentado.")
    return repo.reemplazar_tarifa_aprobada(id_tarifa, usuario_id, motivo)
