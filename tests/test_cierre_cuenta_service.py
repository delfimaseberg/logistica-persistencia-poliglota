from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app.repositories import cierre_cuenta_repository
from app.services import cierre_cuenta_service as service


def _datos_base():
    return {
        "cuenta": {"saldo": Decimal("120.00"), "moneda": "ARS"},
        "apertura": {
            "id_apertura": 9, "id_cliente": 4, "moneda": "ARS",
            "saldo_inicial": Decimal("100.00"),
            "fecha_vigencia": date(2026, 1, 1),
            "referencia_fuente": "conciliación aprobada #A-1",
            "aprobado_por": 2,
            "aprobado_en": datetime(2026, 1, 2, tzinfo=timezone.utc),
        },
        "facturas": [{
            "id_factura": 31, "fecha_emision": date(2026, 3, 4),
            "total": Decimal("50.00"), "estado": "Pendiente", "moneda": "ARS",
        }],
        "pagos": [{
            "id_pago": 41, "id_factura": 31,
            "fecha": datetime(2026, 3, 15, tzinfo=timezone.utc),
            "monto": Decimal("30.00"), "moneda": "ARS",
            "estado_factura": "Parcial",
        }],
        "correcciones": [],
        "movimientos": [
            {"id_movimiento": 1, "moneda": "ARS", "tipo_movimiento": "FACTURA",
             "importe_firmado": Decimal("50.00"), "fecha_contable": date(2026, 3, 4),
             "periodo_origen": date(2026, 3, 1), "tipo_origen": "FACTURA",
             "referencia_origen": "31", "referencia_documental": "f31"},
            {"id_movimiento": 2, "moneda": "ARS", "tipo_movimiento": "PAGO",
             "importe_firmado": Decimal("-30.00"), "fecha_contable": date(2026, 3, 15),
             "periodo_origen": date(2026, 3, 1), "tipo_origen": "PAGO",
             "referencia_origen": "41", "referencia_documental": "p41"},
        ],
        "periodos_cerrados": [],
    }


def test_calcula_snapshot_solo_con_apertura_y_ledger_conciliados():
    data = _datos_base()
    result = service.calcular_snapshot_cierre(data, date(2026, 3, 1))
    assert result == {
        "moneda": "ARS",
        "saldo_inicial": Decimal("100.00"),
        "total_facturas": Decimal("50.00"),
        "total_pagos": Decimal("30.00"),
        "ajustes_netos": Decimal("0.00"),
        "saldo_final": Decimal("120.00"),
        "referencia_saldo_inicial": "conciliación aprobada #A-1",
        "id_apertura": 9,
    }


def test_el_saldo_inicial_del_mes_siguiente_incluye_movimientos_previos():
    data = _datos_base()
    data["cuenta"]["saldo"] = Decimal("140.00")
    data["facturas"].append({
        "id_factura": 30, "fecha_emision": date(2026, 2, 10),
        "total": Decimal("20.00"), "estado": "Pendiente", "moneda": "ARS",
    })
    data["movimientos"].append({
        "id_movimiento": 3, "moneda": "ARS", "tipo_movimiento": "FACTURA",
        "importe_firmado": Decimal("20.00"), "fecha_contable": date(2026, 2, 10),
        "periodo_origen": date(2026, 2, 1), "tipo_origen": "FACTURA",
        "referencia_origen": "30", "referencia_documental": "f30",
    })
    result = service.calcular_snapshot_cierre(data, date(2026, 3, 1))
    assert result["saldo_inicial"] == Decimal("120.00")
    assert result["saldo_final"] == Decimal("140.00")


@pytest.mark.parametrize("change, expected", [
    (lambda d: d.update(apertura=None), "No hay una apertura"),
    (lambda d: d["cuenta"].update(moneda=None), "moneda de la cuenta"),
    (lambda d: d["cuenta"].update(saldo=Decimal("121")), "no concilia"),
    (lambda d: d["movimientos"].pop(), "no tiene movimiento conciliado"),
])
def test_bloquea_apertura_moneda_diferencia_o_ledger_incompleto(change, expected):
    data = _datos_base()
    change(data)
    with pytest.raises(service.CierreBloqueado, match=expected):
        service.calcular_snapshot_cierre(data, date(2026, 3, 1))


def test_bloquea_ajuste_sin_aprobacion_representable():
    data = _datos_base()
    data["movimientos"].append({
        "id_movimiento": 3, "moneda": "ARS", "tipo_movimiento": "AJUSTE",
        "importe_firmado": Decimal("1"), "fecha_contable": date(2026, 3, 20),
        "periodo_origen": date(2026, 3, 1), "tipo_origen": "AJUSTE",
        "referencia_origen": "manual", "referencia_documental": None,
    })
    with pytest.raises(service.CierreBloqueado, match="no tiene aprobación verificable"):
        service.calcular_snapshot_cierre(data, date(2026, 3, 1))


def test_bloquea_cierre_existente_y_no_sobrescribe(monkeypatch):
    monkeypatch.setattr(
        cierre_cuenta_repository, "ejecutar_cierre_atomico",
        lambda *args: (_ for _ in ()).throw(cierre_cuenta_repository.CierreExistente("ya existe")),
    )
    with pytest.raises(service.CierreDuplicado, match="ya existe"):
        service.cerrar_cuenta_mensual(4, date(2026, 3, 1))


def test_reintento_usa_el_repositorio_y_retorna_snapshot_existente_nuevo(monkeypatch):
    calls = []
    result = {"id_cierre": 77, "moneda": "ARS", "saldo_final": Decimal("120")}
    monkeypatch.setattr(
        cierre_cuenta_repository, "ejecutar_cierre_atomico",
        lambda cliente, periodo, calculate: calls.append((cliente, periodo)) or result,
    )
    assert service.cerrar_cuenta_mensual(4, date(2026, 3, 1))["estado"] == "CERRADO"
    assert calls == [(4, date(2026, 3, 1))]


def test_retorna_bloqueo_si_falla_validacion_y_propaga_error_de_repositorio(monkeypatch):
    monkeypatch.setattr(
        cierre_cuenta_repository, "ejecutar_cierre_atomico",
        lambda _cliente, _periodo, calculate: calculate({"cuenta": None}),
    )
    result = service.cerrar_cuenta_mensual(4, date(2026, 3, 1))
    assert result["estado"] == "BLOQUEADO"
    assert "no tiene cuenta" in result["motivo"]

    monkeypatch.setattr(
        cierre_cuenta_repository, "ejecutar_cierre_atomico",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("fallo SQL")),
    )
    with pytest.raises(RuntimeError, match="fallo SQL"):
        service.cerrar_cuenta_mensual(4, date(2026, 3, 1))
