from datetime import date, datetime
from decimal import Decimal

import pytest

from app.utils import validaciones_terceros as v


HOY = date(2026, 10, 30)


# ---------------------------------------------------------------- CUIT

@pytest.mark.parametrize("entrada", ["30-71234567-1", "30712345671", " 30 71234567 1 "])
def test_cuit_valido_se_normaliza(entrada):
    assert v.validar_cuit(entrada) == "30-71234567-1"


@pytest.mark.parametrize("entrada", ["", "30-7123456-1", "abc", "30-71234567-2"])
def test_cuit_invalido_se_rechaza(entrada):
    with pytest.raises(ValueError):
        v.validar_cuit(entrada)


def test_cuit_digito_verificador_cero_y_nueve():
    # Resto 11 -> verificador 0; resto 10 -> verificador 9.
    # 20-00000006: 2*5 + 6*2 = 22 -> resto 0 -> 11 -> verificador 0.
    assert v.validar_cuit("20-00000006-0") == "20-00000006-0"
    # 20-00000001: 2*5 + 1*2 = 12 -> resto 1 -> 10 -> verificador 9.
    assert v.validar_cuit("20-00000001-9") == "20-00000001-9"


# ------------------------------------------------------- modalidades/rubro

def test_modalidades_se_normalizan_sin_repetir():
    assert v.validar_modalidades("aereo, Terrestre, AÉREO") == ["Aéreo", "Terrestre"]
    assert v.validar_modalidades(["maritimo"]) == ["Marítimo"]


@pytest.mark.parametrize("entrada", ["", "ferroviario", []])
def test_modalidades_invalidas(entrada):
    with pytest.raises(ValueError):
        v.validar_modalidades(entrada)


def test_rubro():
    assert v.validar_rubro("seguros") == "SEGUROS"
    with pytest.raises(ValueError):
        v.validar_rubro("transporte")


# --------------------------------------------------------------- fechas

def test_vencimiento_por_defecto_30_dias():
    emision, vencimiento = v.validar_fechas_factura(date(2026, 10, 10), hoy=HOY)
    assert emision == date(2026, 10, 10)
    assert vencimiento == date(2026, 11, 9)


def test_vencimiento_editable():
    _, vencimiento = v.validar_fechas_factura(
        date(2026, 10, 10), date(2026, 10, 25), hoy=HOY
    )
    assert vencimiento == date(2026, 10, 25)


def test_emision_futura_rechazada():
    with pytest.raises(ValueError, match="futura"):
        v.validar_fechas_factura(date(2026, 10, 31), hoy=HOY)


def test_vencimiento_anterior_a_emision_rechazado():
    with pytest.raises(ValueError, match="anterior"):
        v.validar_fechas_factura(date(2026, 10, 10), date(2026, 10, 9), hoy=HOY)


def test_emision_debe_ser_fecha_calendario():
    with pytest.raises(ValueError):
        v.validar_fechas_factura(datetime(2026, 10, 10), hoy=HOY)


# --------------------------------------------------------------- origen

def test_operador_requiere_tramo():
    with pytest.raises(ValueError, match="tramo"):
        v.validar_origen_factura("OPERADOR", None, "flete")
    assert v.validar_origen_factura("OPERADOR", "7", None) == (7, None)


def test_proveedor_requiere_concepto_y_no_tramo():
    with pytest.raises(ValueError, match="concepto"):
        v.validar_origen_factura("PROVEEDOR", None, "  ")
    with pytest.raises(ValueError, match="tramo"):
        v.validar_origen_factura("PROVEEDOR", 3, "Seguro")
    assert v.validar_origen_factura("PROVEEDOR", None, " Seguro ") == (None, "Seguro")


def test_tipo_titular_invalido():
    with pytest.raises(ValueError):
        v.validar_origen_factura("CLIENTE", None, "x")


def test_envio_entregado_ignora_mayusculas():
    assert v.envio_entregado("Entregado")
    assert v.envio_entregado(" ENTREGADO ")
    assert not v.envio_entregado("En tránsito")
    assert not v.envio_entregado(None)


def test_importe_positivo():
    # Mismo redondeo que la cuenta del cliente (Decimal.quantize por defecto).
    assert v.importe_positivo("10.006", "x") == Decimal("10.01")
    assert v.importe_positivo("1500", "x") == Decimal("1500.00")
    with pytest.raises(ValueError):
        v.importe_positivo("0.001", "x")


# ------------------------------------------------------- usuario y parte

def test_usuario_puede_tener_como_mucho_una_parte():
    assert v.validar_partes_usuario(1, None, None) == (1, None, None)
    assert v.validar_partes_usuario(None, None, None) == (None, None, None)
    with pytest.raises(ValueError):
        v.validar_partes_usuario(1, 2, None)
    with pytest.raises(ValueError):
        v.validar_partes_usuario(None, 2, 3)


def test_describir_parte():
    assert v.describir_parte(None, None, None) == "Interno"
    assert v.describir_parte(4, None, None, "Alimentos") == "Cliente: Alimentos"
    assert v.describir_parte(None, 2, None) == "Proveedor ID 2"
    assert v.describir_parte(None, None, 9, "Naviera") == "Operador: Naviera"
