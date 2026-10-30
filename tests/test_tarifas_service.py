from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app.services import tarifas_service


def _datos(componentes=None, cargas=None, tramos=None):
    return {
        "envio": {"id_envio": 12, "estado": "En tránsito"},
        "regla": {"id_regla": 3, "codigo": "REGLA_TEST", "version": 2,
                  "moneda": "TST", "vigente_desde": date(2020, 1, 1),
                  "vigente_hasta": None, "estado": "APROBADA"},
        "componentes": componentes or [{"id_componente": 1, "criterio": "BASE",
                                         "selector": None, "ambito": "ENVIO",
                                         "base_calculo": "FIJO", "importe": "12.30"}],
        "cargas": cargas or [],
        "tramos": tramos or [],
    }


def test_calcular_guarda_snapshot_de_version_y_no_emite_factura(monkeypatch):
    guardado = {}
    monkeypatch.setattr(tarifas_service.repo, "obtener_datos_calculo", lambda *_: _datos())

    def guardar(id_envio, regla, calculo, usuario):
        guardado.update(id_envio=id_envio, regla=regla, calculo=calculo, usuario=usuario)
        return 91, 1, {"regla": {"id_regla": regla["id_regla"], "version": regla["version"]}}

    monkeypatch.setattr(tarifas_service.repo, "guardar_tarifa_borrador", guardar)
    monkeypatch.setattr(
        "app.repositories.facturacion_repository.emitir_factura_envio",
        lambda *_: pytest.fail("calcular tarifa no debe emitir factura"),
    )
    resultado = tarifas_service.calcular_tarifa_envio(12, 3, 7)
    assert resultado["estado"] == "BORRADOR_NO_FACTURABLE"
    assert resultado["importe_base"] == Decimal("12.30")
    assert guardado["calculo"]["entradas"]["envio"]["id_envio"] == 12
    assert guardado["regla"]["version"] == 2


def test_crea_version_de_regla_con_componentes_explicitos(monkeypatch):
    guardado = {}
    monkeypatch.setattr(tarifas_service.repo, "listar_tipos_carga", lambda: [("TEST", "Solo test")])
    monkeypatch.setattr(tarifas_service.repo, "listar_tipos_transporte", lambda: ["TEST_MODE"])
    monkeypatch.setattr(tarifas_service.repo, "crear_regla",
                        lambda *args: guardado.update(args=args) or 52)
    componentes = [
        {"criterio": "BASE", "selector": None, "ambito": "ENVIO",
         "base_calculo": "FIJO", "importe": Decimal("9.25")},
        {"criterio": "CATEGORIA", "selector": "TEST", "ambito": "PARTIDA",
         "base_calculo": "POR_KG", "importe": Decimal("0.125000")},
    ]
    id_regla = tarifas_service.crear_regla(
        "TEST_CARD", 2, "TST", date(2026, 1, 1), None, 7, componentes
    )
    assert id_regla == 52
    assert guardado["args"][1] == 2
    assert guardado["args"][-1] == componentes


def test_datos_faltantes_no_persisten_tarifa(monkeypatch):
    datos = _datos(
        componentes=[
            {"criterio": "BASE", "selector": None, "ambito": "ENVIO",
             "base_calculo": "FIJO", "importe": "1.00"},
            {"criterio": "PESO", "selector": None, "ambito": "ENVIO",
             "base_calculo": "POR_KG", "importe": "1.00"},
        ]
    )
    monkeypatch.setattr(tarifas_service.repo, "obtener_datos_calculo", lambda *_: datos)
    monkeypatch.setattr(
        tarifas_service.repo, "guardar_tarifa_borrador",
        lambda *_: pytest.fail("no debe persistir un cálculo incompleto"),
    )
    with pytest.raises(ValueError, match="partidas de carga"):
        tarifas_service.calcular_tarifa_envio(12, 3, 7)


def test_aprobacion_reutiliza_validacion_fiscal_y_guarda_snapshot(monkeypatch):
    hoy = date.today()
    fiscal = (4, "FISCAL_TEST", 1, "TRATAMIENTO_TEST", None,
              date(2020, 1, 1), None, "fuente-fiscal-test", 8,
              datetime(2026, 1, 1, tzinfo=timezone.utc), True)
    llamado = {}
    monkeypatch.setattr(tarifas_service.repo, "cargar_borrador_tarifa", lambda _: {
        "id_tarifa": 91, "id_envio": 12, "version": 1,
        "importe_base": Decimal("12.30"), "id_regla": 3,
        "detalle_calculo": {"regla": {"id_regla": 3, "moneda": "TST"}}, "estado": "BORRADOR",
        "moneda_cuenta": "TST",
    })
    monkeypatch.setattr(tarifas_service.repo, "listar_configuraciones_fiscales", lambda: [fiscal])
    monkeypatch.setattr(tarifas_service.repo, "aprobar_tarifa",
                        lambda *args: llamado.update(args=args))
    tarifas_service.aprobar_tarifa_envio(91, 4, "0.00", "12.30", "acta-test", 7)
    assert llamado["args"][0] == 91
    assert llamado["args"][1]["importe_total"] == Decimal("12.30")
    assert llamado["args"][2:] == (7, "acta-test")


def test_sin_moneda_de_cuenta_no_aprueba(monkeypatch):
    fiscal = (4, "FISCAL_TEST", 1, "TRATAMIENTO_TEST", None,
              date(2020, 1, 1), None, "fuente-fiscal-test", 8,
              datetime(2026, 1, 1, tzinfo=timezone.utc), True)
    monkeypatch.setattr(tarifas_service.repo, "cargar_borrador_tarifa", lambda _: {
        "importe_base": Decimal("12.30"), "estado": "BORRADOR", "moneda_cuenta": None,
        "detalle_calculo": {"regla": {"moneda": "TST"}},
    })
    monkeypatch.setattr(tarifas_service.repo, "listar_configuraciones_fiscales", lambda: [fiscal])
    with pytest.raises(ValueError, match="moneda de la regla"):
        tarifas_service.aprobar_tarifa_envio(91, 4, "0", "12.30", "acta-test", 7)


def test_sin_perfil_fiscal_no_aprueba_tarifa(monkeypatch):
    monkeypatch.setattr(tarifas_service.repo, "cargar_borrador_tarifa", lambda _: {
        "importe_base": Decimal("12.30"), "estado": "BORRADOR", "moneda_cuenta": "TST",
        "detalle_calculo": {"regla": {"moneda": "TST"}},
    })
    monkeypatch.setattr(tarifas_service.repo, "listar_configuraciones_fiscales", lambda: [])
    monkeypatch.setattr(tarifas_service.repo, "aprobar_tarifa",
                        lambda *_: pytest.fail("sin perfil fiscal no se debe aprobar"))
    with pytest.raises(ValueError, match="configuración fiscal activa"):
        tarifas_service.aprobar_tarifa_envio(91, 404, "0", "12.30", "acta-test", 7)
