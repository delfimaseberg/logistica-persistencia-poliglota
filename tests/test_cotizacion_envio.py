from decimal import Decimal

import pytest

from app.services import cotizacion_envio as cot


def componentes(base="1000", terrestre="5000", maritimo="20000", aereo="40000"):
    filas = [{"id_componente": 1, "criterio": "BASE", "selector": None,
              "ambito": "ENVIO", "base_calculo": "FIJO", "importe": Decimal(base)}]
    for i, (medio, precio) in enumerate(
        [("Terrestre", terrestre), ("Marítimo", maritimo), ("Aéreo", aereo)], 2
    ):
        if precio is not None:
            filas.append({"id_componente": i, "criterio": "TRANSPORTE",
                          "selector": medio, "ambito": "TRAMO",
                          "base_calculo": "FIJO", "importe": Decimal(precio)})
    return filas


TRAMOS = [
    {"id_tramo": 10, "medio_transporte": "Terrestre", "origen": "Buenos Aires",
     "destino": "Rosario"},
    {"id_tramo": 11, "medio_transporte": "Marítimo", "origen": "Rosario",
     "destino": "Montevideo"},
    {"id_tramo": 12, "medio_transporte": "Terrestre", "origen": "Montevideo",
     "destino": "Colonia"},
]


def test_cotizacion_base_mas_un_precio_por_tramo_mas_iva():
    r = cot.cotizar(TRAMOS, componentes())
    # 1000 + 5000 + 20000 + 5000 = 31000; IVA 21 % = 6510
    assert r["neto"] == Decimal("31000.00")
    assert r["iva"] == Decimal("6510.00")
    assert r["total"] == Decimal("37510.00")
    assert r["moneda"] == "ARS" and r["tratamiento"] == "IVA_21"


def test_lineas_base_primero_y_tramos_en_orden_del_recorrido():
    r = cot.cotizar(TRAMOS, componentes())
    assert [(l["linea"], l["concepto"], l["id_tramo"]) for l in r["lineas"]] == [
        (1, "BASE", None), (2, "TRAMO", 10), (3, "TRAMO", 11), (4, "TRAMO", 12),
    ]
    assert r["lineas"][2]["medio_transporte"] == "Marítimo"
    assert sum(l["importe"] for l in r["lineas"]) == r["neto"]


def test_iva_redondea_mitad_hacia_arriba():
    assert cot.calcular_iva(Decimal("0.50")) == Decimal("0.11")   # 0.105
    assert cot.calcular_iva(Decimal("10.10")) == Decimal("2.12")  # 2.121


def test_sin_tramos_no_se_cotiza():
    with pytest.raises(cot.CotizacionImposible, match="tramos"):
        cot.cotizar([], componentes())


def test_sin_tarifa_no_se_cotiza():
    with pytest.raises(cot.CotizacionImposible, match="tarifa"):
        cot.cotizar(TRAMOS, [])


def test_medio_sin_precio_bloquea_en_vez_de_cobrar_de_menos():
    with pytest.raises(cot.CotizacionImposible, match="Marítimo"):
        cot.cotizar(TRAMOS, componentes(maritimo=None))


def test_regla_estandar_no_admite_otros_criterios():
    filas = componentes() + [{"id_componente": 9, "criterio": "PESO",
                              "selector": None, "ambito": "ENVIO",
                              "base_calculo": "POR_KG", "importe": Decimal("1")}]
    with pytest.raises(cot.CotizacionImposible, match="PESO"):
        cot.cotizar(TRAMOS, filas)


def test_base_cero_permitida_pero_total_debe_ser_positivo():
    r = cot.cotizar(TRAMOS[:1], componentes(base="0"))
    assert r["neto"] == Decimal("5000.00")
    with pytest.raises(cot.CotizacionImposible, match="mayor a cero"):
        cot.cotizar(TRAMOS[:1], componentes(base="0", terrestre="0"))
