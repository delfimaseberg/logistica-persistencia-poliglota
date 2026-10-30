from pathlib import Path
from unittest.mock import patch

import pytest

from app.services import facturacion_automatica_service as service


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
