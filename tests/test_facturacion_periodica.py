from pathlib import Path
from unittest.mock import patch

import pytest

from app.services import facturacion_automatica_service as service


def test_revisar_envios_devuelve_candidatos_sin_emitir_facturas():
    with patch.object(
        service,
        "listar_envios_entregados_candidatos_facturacion",
        return_value=[(17, 4, "Entregado")],
    ) as listar:
        resultado = service.revisar_envios_potencialmente_facturables()

    listar.assert_called_once_with()
    assert resultado["candidatos"] == [{
        "id_envio": 17,
        "id_cliente": 4,
        "estado": "Entregado",
    }]
    assert resultado["facturas_emitidas"] == 0
    assert resultado["bloqueado"] is True
    assert len(resultado["motivos"]) == 2


def test_revision_sin_envios_no_habilita_emision_ni_inventa_importes():
    with patch.object(
        service,
        "listar_envios_entregados_candidatos_facturacion",
        return_value=[],
    ):
        resultado = service.revisar_envios_potencialmente_facturables()

    assert resultado["candidatos"] == []
    assert resultado["facturas_emitidas"] == 0
    assert resultado["bloqueado"] is True
    assert any("importe" in motivo for motivo in resultado["motivos"])


def test_reejecucion_sigue_siendo_solo_lectura_y_no_emite_facturas():
    with patch.object(
        service,
        "listar_envios_entregados_candidatos_facturacion",
        return_value=[(17, 4, "Entregado")],
    ) as listar:
        primera = service.revisar_envios_potencialmente_facturables()
        segunda = service.revisar_envios_potencialmente_facturables()

    assert primera == segunda
    assert primera["facturas_emitidas"] == segunda["facturas_emitidas"] == 0
    assert listar.call_count == 2


def test_error_al_listar_candidatos_se_propaga():
    with patch.object(
        service,
        "listar_envios_entregados_candidatos_facturacion",
        side_effect=RuntimeError("PostgreSQL no disponible"),
    ):
        with pytest.raises(RuntimeError, match="PostgreSQL no disponible"):
            service.revisar_envios_potencialmente_facturables()


def test_migracion_define_unicidad_cliente_periodo_sin_aplicarla():
    ruta = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "migrations"
        / "002_cierres_cuenta_corriente.sql"
    )
    sql = ruta.read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS cierre_cuenta_corriente" in sql
    assert "UNIQUE (id_cliente, periodo)" in sql
    assert "referencia_saldo_inicial TEXT NOT NULL" in sql
