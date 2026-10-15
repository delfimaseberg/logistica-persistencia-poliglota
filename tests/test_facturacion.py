
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from app.repositories import facturacion_repository as repo
from app.services import facturacion_service as service


def test_importe_cero_no_permitido():
    with pytest.raises(ValueError, match="mayor a cero"):
        repo.emitir_factura(1, Decimal("0"))


def test_importe_negativo_no_permitido():
    with pytest.raises(ValueError, match="mayor a cero"):
        repo.emitir_factura(1, Decimal("-100"))


def test_pago_cero_no_permitido():
    with pytest.raises(ValueError, match="mayor a cero"):
        repo.registrar_pago(1, Decimal("0"), "Efectivo")


def test_pago_negativo_no_permitido():
    with pytest.raises(ValueError, match="mayor a cero"):
        repo.registrar_pago(1, Decimal("-50"), "Efectivo")


def test_formato_dinero():
    assert service.dinero(Decimal("1500.50")) == "$1,500.50"


def test_seleccionar_elemento_por_numero():
    elementos = ["Cliente A", "Cliente B"]

    with patch("builtins.input", return_value="2"):
        seleccionado = service.seleccionar_elemento(
            elementos,
            "CLIENTES",
            lambda elemento: elemento
        )

    assert seleccionado == "Cliente B"


def test_cancelar_seleccion():
    with patch("builtins.input", return_value="0"):
        seleccionado = service.seleccionar_elemento(
            ["Cliente A"],
            "CLIENTES",
            lambda elemento: elemento
        )

    assert seleccionado is None


def test_pago_superior_al_pendiente_se_rechaza():
    cursor = MagicMock()
    cursor.fetchone.side_effect = [
        (2, Decimal("100.00"), "Pendiente"),
        (Decimal("20.00"),)
    ]

    conexion = MagicMock()
    conexion.__enter__.return_value = conexion
    conexion.cursor.return_value.__enter__.return_value = cursor

    with patch.object(repo, "get_postgres_connection", return_value=conexion):
        with pytest.raises(ValueError, match="supera"):
            repo.registrar_pago(1, Decimal("90.00"), "Transferencia")

    assert not any(
        "INSERT INTO pago" in str(llamada)
        for llamada in cursor.execute.call_args_list
    )


def test_factura_inexistente_no_permite_pago():
    cursor = MagicMock()
    cursor.fetchone.return_value = None

    conexion = MagicMock()
    conexion.__enter__.return_value = conexion
    conexion.cursor.return_value.__enter__.return_value = cursor

    with patch.object(repo, "get_postgres_connection", return_value=conexion):
        with pytest.raises(ValueError, match="no existe"):
            repo.registrar_pago(999, Decimal("100"), "Efectivo")
