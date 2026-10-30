from decimal import Decimal

import pytest

from app.services.tarifas_calculo import (
    CalculoTarifaInvalido,
    calcular_componentes,
    validar_estructura_componentes,
)


def _componente(criterio, base, importe, ambito, selector=None):
    return {
        "id_componente": criterio + str(selector or ""),
        "criterio": criterio,
        "selector": selector,
        "ambito": ambito,
        "base_calculo": base,
        "importe": Decimal(importe),
    }


def test_calcula_base_peso_distancia_categoria_fragilidad_y_transporte():
    reglas = [
        _componente("BASE", "FIJO", "100.00", "ENVIO"),
        _componente("PESO", "POR_KG", "2.00", "ENVIO"),
        _componente("DISTANCIA", "POR_KM", "1.50", "ENVIO"),
        _componente("CATEGORIA", "FIJO", "7.00", "PARTIDA", "DEFINIDA_EN_TEST"),
        _componente("FRAGIL", "POR_KG", "0.10", "PARTIDA", "true"),
        _componente("TRANSPORTE", "POR_KM", "0.50", "TRAMO", "TEST_TRANSPORTE"),
    ]
    resultado = calcular_componentes(
        [
            {"id_envio_carga": 1, "tipo_carga": "DEFINIDA_EN_TEST", "peso_kg": "10", "fragil": True},
            {"id_envio_carga": 2, "tipo_carga": "OTRA_TEST", "peso_kg": "5", "fragil": False},
        ],
        [
            {"id_tramo": 10, "medio_transporte": "TEST_TRANSPORTE", "distancia_km": "3"},
        ],
        reglas,
    )
    assert resultado["importe_base"] == Decimal("144.00")
    assert len(resultado["detalle"]) == 6


@pytest.mark.parametrize(
    "cargas,tramos,reglas,mensaje",
    [
        ([], [], [_componente("BASE", "FIJO", "1.00", "ENVIO"),
                  _componente("PESO", "POR_KG", "2.00", "ENVIO")], "partidas de carga"),
        ([{"peso_kg": "2", "tipo_carga": "TEST", "fragil": False}],
         [{"id_tramo": 1, "distancia_km": None}],
         [_componente("BASE", "FIJO", "1.00", "ENVIO"),
          _componente("DISTANCIA", "POR_KM", "2.00", "ENVIO")], "distancia"),
        ([], [], [_componente("BASE", "FIJO", "1.00", "ENVIO"),
                  _componente("PESO", "POR_KG", "1.00", "ENVIO"),
                  _componente("PESO", "POR_KG", "2.00", "ENVIO")], "incompatible"),
    ],
)
def test_bloquea_datos_faltantes_y_reglas_ambiguas(cargas, tramos, reglas, mensaje):
    with pytest.raises(CalculoTarifaInvalido, match=mensaje):
        calcular_componentes(cargas, tramos, reglas)


def test_no_redondea_silenciosamente_resultado_fuera_de_centavos():
    reglas = [_componente("BASE", "FIJO", "0.005", "ENVIO")]
    with pytest.raises(CalculoTarifaInvalido, match="redondeo"):
        calcular_componentes([], [], reglas)


def test_version_de_regla_requiere_base_unica_y_combinaciones_soportadas():
    validar_estructura_componentes([_componente("BASE", "FIJO", "0.00", "ENVIO")])
    with pytest.raises(CalculoTarifaInvalido, match="exactamente un componente base"):
        validar_estructura_componentes([])
    with pytest.raises(CalculoTarifaInvalido, match="requiere selector"):
        validar_estructura_componentes([
            _componente("BASE", "FIJO", "1", "ENVIO"),
            _componente("TRANSPORTE", "POR_KM", "1", "TRAMO"),
        ])


def test_no_permite_sumar_dos_bases_para_la_misma_categoria_sin_regla_explicita():
    with pytest.raises(CalculoTarifaInvalido, match="no se aplica prioridad ni acumulación"):
        validar_estructura_componentes([
            _componente("BASE", "FIJO", "1.00", "ENVIO"),
            _componente("CATEGORIA", "FIJO", "1.00", "PARTIDA", "TEST"),
            _componente("CATEGORIA", "POR_KG", "2.00", "PARTIDA", "TEST"),
        ])
