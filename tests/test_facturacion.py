
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from app.repositories import facturacion_repository as repo
from app.services import facturacion_service as service


def crear_conexion_mock(cursor):
    conexion = MagicMock()
    conexion.__enter__.return_value = conexion
    conexion.cursor.return_value.__enter__.return_value = cursor
    return conexion


def test_pago_cero_no_permitido():
    with pytest.raises(ValueError, match="mayor a cero"):
        repo.registrar_pago(1, Decimal("0"), "Efectivo")


def test_pago_negativo_no_permitido():
    with pytest.raises(ValueError, match="mayor a cero"):
        repo.registrar_pago(1, Decimal("-50"), "Efectivo")


def test_formato_dinero():
    assert service.dinero(Decimal("1500.50")) == "$1.500,50"


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
    conexion = crear_conexion_mock(cursor)

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
    conexion = crear_conexion_mock(cursor)

    with patch.object(repo, "get_postgres_connection", return_value=conexion):
        with pytest.raises(ValueError, match="no existe"):
            repo.registrar_pago(999, Decimal("100"), "Efectivo")


# ---------------------------------------------------------------------------
# Registro de movimientos financieros (factura manual y pago)
# ---------------------------------------------------------------------------

def _conexion_con_cursor(respuestas):
    cursor = MagicMock()
    cursor.fetchone.side_effect = respuestas
    cursor.rowcount = 1
    conexion = MagicMock()
    conexion.__enter__.return_value = conexion
    conexion.cursor.return_value.__enter__.return_value = cursor
    return conexion, cursor


def _sentencias(cursor):
    return [
        (str(llamada.args[0]), llamada.args[1] if len(llamada.args) > 1 else None)
        for llamada in cursor.execute.call_args_list
    ]


def test_pago_manual_debe_registrar_movimiento_negativo():
    from datetime import date

    conexion, cursor = _conexion_con_cursor([
        (7, Decimal("100.00"), "Pendiente"),  # factura bloqueada
        (Decimal("20.00"),),                  # ya pagado
        ("ARS",),                             # moneda de la factura
        ("ARS",),                             # moneda de la cuenta (bloqueada)
        (88, date(2026, 10, 29)),             # pago insertado
    ])

    with patch.object(repo, "get_postgres_connection", return_value=conexion):
        id_pago, estado = repo.registrar_pago(3, Decimal("80.00"), "Efectivo")

    assert (id_pago, estado) == (88, "Pagada")
    sentencias = _sentencias(cursor)
    movimiento = [p for sql, p in sentencias
                  if "INSERT INTO movimiento_cuenta_corriente" in sql]
    assert len(movimiento) == 1
    id_cliente, moneda, importe, fecha, referencia, _ = movimiento[0]
    assert (id_cliente, moneda, importe, fecha, referencia) == (
        7, "ARS", Decimal("-80.00"), date(2026, 10, 29), "88"
    )
    assert any("UPDATE cuenta_corriente" in sql for sql, _ in sentencias)
    assert conexion.__exit__.call_args.args == (None, None, None)


def test_pago_de_factura_sin_moneda_no_escribe():
    conexion, cursor = _conexion_con_cursor([
        (7, Decimal("100.00"), "Pendiente"),
        (Decimal("0"),),
        (None,),
    ])

    with patch.object(repo, "get_postgres_connection", return_value=conexion):
        with pytest.raises(ValueError, match="moneda"):
            repo.registrar_pago(3, Decimal("10"), "Efectivo")

    assert not any("INSERT" in sql for sql, _ in _sentencias(cursor))


def test_reportes_agregan_pagos_antes_de_unir():
    import inspect

    for funcion in (repo.reporte_facturacion_clientes,
                    repo.consultar_cuenta_corriente):
        sql = inspect.getsource(funcion)
        assert "WITH facturado AS" in sql
        assert "LEFT JOIN factura f ON f.id_cliente = c.id_cliente" not in sql
