"""Casos de uso de reglas tarifarias y tarifas por envío."""

from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from app.repositories import tarifas_repository as repo
from app.services.tarifas_calculo import (
    CalculoTarifaInvalido,
    calcular_componentes,
    validar_estructura_componentes,
)
from app.utils.validaciones_financieras import validar_tarifa_aprobada


def _hoy_buenos_aires():
    return datetime.now(ZoneInfo("America/Argentina/Buenos_Aires")).date()


def registrar_tipo_carga(codigo, descripcion):
    codigo = str(codigo or "").strip().upper()
    descripcion = str(descripcion or "").strip()
    if not codigo or len(codigo) > 40 or not descripcion:
        raise ValueError("El código y la descripción de la categoría son obligatorios.")
    return repo.crear_tipo_carga(codigo, descripcion)


def registrar_partida_carga(id_envio, tipo_carga, peso_kg, fragil, descripcion=None):
    try:
        peso = Decimal(str(peso_kg))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("El peso real debe ser un decimal válido en kg.")
    if not peso.is_finite() or peso <= 0:
        raise ValueError("El peso real debe ser mayor a cero.")
    if max(0, -peso.as_tuple().exponent) > 3:
        raise ValueError("El peso admite hasta tres decimales de kg.")
    if not isinstance(fragil, bool):
        raise ValueError("La fragilidad debe indicarse explícitamente.")
    return repo.agregar_carga(id_envio, tipo_carga, peso, fragil, descripcion)


def registrar_distancia_tramo(id_tramo, distancia_km):
    try:
        distancia = Decimal(str(distancia_km))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("La distancia debe ser un decimal válido en km.")
    if not distancia.is_finite() or distancia <= 0:
        raise ValueError("La distancia debe ser mayor a cero.")
    if max(0, -distancia.as_tuple().exponent) > 3:
        raise ValueError("La distancia admite hasta tres decimales de km.")
    if not repo.actualizar_distancia_tramo(id_tramo, distancia):
        raise ValueError("No existe ese tramo.")


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
    return repo.crear_regla(codigo, int(version), moneda, desde, hasta,
                            usuario_id, componentes)


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


def calcular_tarifa_envio(id_envio, id_regla, usuario_id):
    datos = repo.obtener_datos_calculo(id_envio, id_regla)
    hoy = _hoy_buenos_aires()
    regla = datos["regla"]
    if regla["vigente_desde"] > hoy or (
        regla["vigente_hasta"] is not None and regla["vigente_hasta"] < hoy
    ):
        raise ValueError("La regla aprobada no está vigente hoy.")
    validar_estructura_componentes(datos["componentes"])
    calculo = calcular_componentes(datos["cargas"], datos["tramos"], datos["componentes"])
    entradas = {
        "envio": datos["envio"],
        "cargas": datos["cargas"],
        "tramos": datos["tramos"],
    }
    calculo["entradas"] = entradas
    id_tarifa, version, snapshot = repo.guardar_tarifa_borrador(
        id_envio, regla, calculo, usuario_id
    )
    return {
        "id_tarifa": id_tarifa,
        "version_tarifa": version,
        "id_envio": id_envio,
        "regla": regla,
        "importe_base": calculo["importe_base"],
        "detalle": calculo["detalle"],
        "snapshot": snapshot,
        "estado": "BORRADOR_NO_FACTURABLE",
        "motivo": (
            "El importe es el subtotal comercial calculado. La tarifa no está aprobada; "
            "requiere moneda de cuenta y configuración fiscal aprobada antes de facturar."
        ),
    }


def aprobar_tarifa_envio(id_tarifa, id_configuracion_fiscal, importe_impuestos,
                         importe_total, referencia, usuario_id):
    borrador = repo.cargar_borrador_tarifa(id_tarifa)
    if not borrador or borrador["estado"] != "BORRADOR":
        raise ValueError("La tarifa no existe o no está en borrador.")
    perfiles = repo.listar_configuraciones_fiscales()
    fila = next((x for x in perfiles if x[0] == id_configuracion_fiscal), None)
    if fila is None:
        raise ValueError("No existe una configuración fiscal activa para esa selección.")
    snapshot = borrador.get("detalle_calculo") or {}
    regla_snapshot = snapshot.get("regla", {}) if isinstance(snapshot, dict) else {}
    moneda_regla = regla_snapshot.get("moneda")
    if not moneda_regla or str(moneda_regla).upper() != str(borrador["moneda_cuenta"] or "").upper():
        raise ValueError("La moneda de la regla no coincide con la moneda configurada de la cuenta.")
    perfil = {
        "id_configuracion_fiscal": fila[0], "codigo": fila[1], "version": fila[2],
        "tratamiento": fila[3], "tasa": fila[4], "vigente_desde": fila[5],
        "vigente_hasta": fila[6], "referencia_aprobacion": fila[7],
        "aprobado_por": fila[8], "aprobado_en": fila[9], "aprobada": True,
        "activa": fila[10],
    }
    try:
        impuestos = Decimal(str(importe_impuestos))
        total = Decimal(str(importe_total))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("Los importes fiscales y el total deben ser decimales válidos.")
    if not impuestos.is_finite() or impuestos < 0 or not total.is_finite() or total <= 0:
        raise ValueError("Los importes fiscales o el total no son válidos.")
    if max(0, -impuestos.as_tuple().exponent) > 2 or max(0, -total.as_tuple().exponent) > 2:
        raise ValueError("Los importes fiscales y el total admiten hasta dos decimales.")
    ahora = datetime.now(timezone.utc)
    tarifa = {
        "estado": "APROBADA", "moneda": borrador["moneda_cuenta"],
        "importe_base": borrador["importe_base"], "importe_impuestos": impuestos,
        "importe_total": total, "tratamiento_impositivo": perfil["tratamiento"],
        "tasa_impositiva": perfil["tasa"],
        "referencia_aprobacion": referencia, "aprobado_por": usuario_id,
        "aprobado_en": ahora, "id_configuracion_fiscal": id_configuracion_fiscal,
    }
    validar_tarifa_aprobada(tarifa, borrador["moneda_cuenta"], perfil, _hoy_buenos_aires())
    if not str(referencia or "").strip():
        raise ValueError("La aprobación requiere una referencia documentada.")
    valores = {
        "importe_impuestos": impuestos, "importe_total": total,
        "moneda": borrador["moneda_cuenta"],
        "id_configuracion_fiscal": id_configuracion_fiscal,
        "tratamiento_impositivo": perfil["tratamiento"],
        "tasa_impositiva": perfil["tasa"],
    }
    repo.aprobar_tarifa(id_tarifa, valores, usuario_id, str(referencia).strip())


def obtener_detalle_tarifa(id_tarifa):
    tarifa = repo.obtener_tarifa(id_tarifa)
    if tarifa is None:
        raise ValueError("No existe esa tarifa.")
    return tarifa


def reemplazar_tarifa_aprobada(id_tarifa, usuario_id, motivo):
    """Solicita el único cambio de estado autorizado para una tarifa aprobada."""
    if not usuario_id or not str(motivo or "").strip():
        raise ValueError("El reemplazo requiere usuario y motivo documentado.")
    return repo.reemplazar_tarifa_aprobada(id_tarifa, usuario_id, motivo)
