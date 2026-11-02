from datetime import date
from decimal import Decimal

from app.services import tarifas_service


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


