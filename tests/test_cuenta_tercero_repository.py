from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from app.repositories import cuenta_tercero_repository as repo


HOY = date(2026, 10, 30)
ENTREGA = date(2026, 10, 18)


def crear_conexion_mock(cursor):
    conexion = MagicMock()
    conexion.__enter__.return_value = conexion
    conexion.cursor.return_value.__enter__.return_value = cursor
    return conexion


def cursor_con(*respuestas, rowcount=1):
    cursor = MagicMock()
    cursor.fetchone.side_effect = list(respuestas)
    cursor.rowcount = rowcount
    return cursor


def sqls(cursor):
    return [c.args[0] for c in cursor.execute.call_args_list]


def ejecutar(cursor, funcion, *args, **kwargs):
    with patch.object(
        repo, "get_postgres_connection",
        return_value=crear_conexion_mock(cursor),
    ):
        return funcion(*args, **kwargs)


def factura_operador(cursor, **extra):
    datos = dict(
        tipo_titular="OPERADOR", id_titular=7,
        numero_comprobante="a-0001-00000010", total="1500",
        fecha_emision=date(2026, 10, 20), id_tramo=3, hoy=HOY,
    )
    datos.update(extra)
    return ejecutar(cursor, repo.registrar_factura_recibida, **datos)


# ------------------------------------------------- factura de operador

def test_factura_operador_ok_suma_saldo_y_movimiento_positivo():
    cursor = cursor_con(
        ("ACTIVO",),            # titular
        (7, "Entregado", ENTREGA),  # tramo del operador, envío entregado
        None,                   # sin factura vigente para el tramo
        None,                   # comprobante no repetido
        (10, "ARS"),            # cuenta existente
        (99,),                  # id de la factura
    )

    assert factura_operador(cursor) == 99

    ejecutadas = sqls(cursor)
    insert_factura = next(s for s in ejecutadas if "INSERT INTO factura_recibida" in s)
    assert "id_operador" in insert_factura

    params_factura = cursor.execute.call_args_list[ejecutadas.index(insert_factura)].args[1]
    # comprobante normalizado, vencimiento por defecto a 30 días, tramo.
    assert params_factura[1] == "A-0001-00000010"
    assert params_factura[3] == date(2026, 11, 19)
    assert params_factura[4] == Decimal("1500.00")
    assert params_factura[6] == 3

    i_saldo = next(i for i, s in enumerate(ejecutadas) if "saldo = saldo + %s" in s)
    assert cursor.execute.call_args_list[i_saldo].args[1] == (Decimal("1500.00"), 10)

    i_mov = next(i for i, s in enumerate(ejecutadas) if "INSERT INTO movimiento_cuenta_tercero" in s)
    assert "'FACTURA_RECIBIDA'" in ejecutadas[i_mov]
    params_mov = cursor.execute.call_args_list[i_mov].args[1]
    assert params_mov[2] == Decimal("1500.00")      # positivo: aumenta la deuda
    assert params_mov[3] == date(2026, 10, 20)      # fecha contable = emisión


def test_factura_operador_crea_cuenta_si_no_existe():
    cursor = cursor_con(
        ("ACTIVO",), (7, "Entregado", ENTREGA), None, None,
        None,                   # no hay cuenta
        (11, "ARS"),            # se crea
        (100,),
    )
    assert factura_operador(cursor) == 100
    assert any("INSERT INTO cuenta_corriente_tercero" in s for s in sqls(cursor))


@pytest.mark.parametrize("estado", ["En tránsito", "Pendiente", "Cancelado"])
def test_factura_operador_rechazada_si_envio_no_entregado(estado):
    cursor = cursor_con(("ACTIVO",), (7, estado, None))
    with pytest.raises(ValueError, match="Entregado"):
        factura_operador(cursor)
    assert not any("INSERT" in s for s in sqls(cursor))


def test_factura_operador_anterior_a_la_entrega_rechazada():
    # La factura (20/10) no puede ser anterior a la entrega del envío.
    cursor = cursor_con(("ACTIVO",), (7, "Entregado", date(2026, 10, 25)))
    with pytest.raises(ValueError, match="anterior a la entrega"):
        factura_operador(cursor)
    assert not any("INSERT" in s for s in sqls(cursor))


def test_factura_operador_exige_fecha_real_de_entrega():
    cursor = cursor_con(("ACTIVO",), (7, "Entregado", None))
    with pytest.raises(ValueError, match="fecha real de entrega"):
        factura_operador(cursor)


def test_factura_operador_rechazada_si_tramo_es_de_otro_operador():
    cursor = cursor_con(("ACTIVO",), (8, "Entregado", ENTREGA))
    with pytest.raises(ValueError, match="no fue realizado por este operador"):
        factura_operador(cursor)


def test_factura_operador_rechazada_si_tramo_sin_operador():
    cursor = cursor_con(("ACTIVO",), (None, "Entregado", ENTREGA))
    with pytest.raises(ValueError, match="no tiene operador"):
        factura_operador(cursor)


def test_una_factura_por_tramo():
    cursor = cursor_con(("ACTIVO",), (7, "Entregado", ENTREGA), (1,))
    with pytest.raises(ValueError, match="ya tiene una factura"):
        factura_operador(cursor)
    assert not any("INSERT" in s for s in sqls(cursor))


def test_comprobante_duplicado_rechazado():
    cursor = cursor_con(("ACTIVO",), (7, "Entregado", ENTREGA), None, (1,))
    with pytest.raises(ValueError, match="comprobante ya fue registrado"):
        factura_operador(cursor)


def test_titular_inactivo_no_recibe_facturas():
    cursor = cursor_con(("INACTIVO",))
    with pytest.raises(ValueError, match="inactivo"):
        factura_operador(cursor)


def test_titular_inexistente():
    cursor = cursor_con(None)
    with pytest.raises(ValueError, match="no existe"):
        factura_operador(cursor)


def test_operador_sin_tramo_se_rechaza_antes_de_la_base():
    cursor = cursor_con()
    with pytest.raises(ValueError, match="tramo"):
        factura_operador(cursor, id_tramo=None)
    cursor.execute.assert_not_called()


# ------------------------------------------------- factura de proveedor

def test_factura_proveedor_con_concepto_sin_tramo():
    cursor = cursor_con(("ACTIVO",), None, (20, "ARS"), (55,))
    resultado = ejecutar(
        cursor, repo.registrar_factura_recibida,
        "PROVEEDOR", 2, "B-1", Decimal("40000"), date(2026, 10, 1),
        concepto="Póliza de carga", hoy=HOY,
    )
    assert resultado == 55
    ejecutadas = sqls(cursor)
    assert not any("FROM tramo" in s for s in ejecutadas)
    insert = next(s for s in ejecutadas if "INSERT INTO factura_recibida" in s)
    assert "id_proveedor" in insert


def test_factura_proveedor_sin_concepto_rechazada():
    cursor = cursor_con()
    with pytest.raises(ValueError, match="concepto"):
        ejecutar(
            cursor, repo.registrar_factura_recibida,
            "PROVEEDOR", 2, "B-1", 100, date(2026, 10, 1), hoy=HOY,
        )
    cursor.execute.assert_not_called()


@pytest.mark.parametrize("importe", ["0", "-5", "0.001", "abc"])
def test_importe_invalido(importe):
    cursor = cursor_con()
    with pytest.raises(ValueError):
        factura_operador(cursor, total=importe)
    cursor.execute.assert_not_called()


# ----------------------------------------------------------------- pagos

def pago(cursor, monto, **extra):
    return ejecutar(
        cursor, repo.registrar_pago_emitido, 5, monto, "Transferencia", **extra
    )


def test_pago_parcial_resta_saldo_y_movimiento_negativo():
    cursor = cursor_con(
        (None, 7, Decimal("1000.00"), "Pendiente", "ARS"),
        (Decimal("0"),),
        (10, "ARS"),
        (31, date(2026, 10, 30)),
    )
    assert pago(cursor, "400") == (31, "Parcial")

    ejecutadas = sqls(cursor)
    i_saldo = next(i for i, s in enumerate(ejecutadas) if "saldo = saldo - %s" in s)
    assert cursor.execute.call_args_list[i_saldo].args[1] == (Decimal("400.00"), 10)
    i_mov = next(i for i, s in enumerate(ejecutadas) if "INSERT INTO movimiento_cuenta_tercero" in s)
    assert "'PAGO_EMITIDO'" in ejecutadas[i_mov]
    assert cursor.execute.call_args_list[i_mov].args[1][2] == Decimal("-400.00")
    # La cuenta buscada es la del operador de la factura.
    assert any("WHERE id_operador = %s" in s and "cuenta_corriente_tercero" in s
               for s in ejecutadas)


def test_pago_del_pendiente_deja_pagada():
    cursor = cursor_con(
        (2, None, Decimal("1000.00"), "Parcial", "ARS"),
        (Decimal("400.00"),),
        (20, "ARS"),
        (32, date(2026, 10, 30)),
    )
    assert pago(cursor, "600") == (32, "Pagada")


def test_pago_mayor_al_pendiente_rechazado():
    cursor = cursor_con(
        (None, 7, Decimal("1000.00"), "Parcial", "ARS"),
        (Decimal("400.00"),),
    )
    with pytest.raises(ValueError, match="supera el saldo pendiente"):
        pago(cursor, "600.01")
    assert not any("INSERT" in s for s in sqls(cursor))


def test_pago_sobre_factura_pagada_rechazado():
    cursor = cursor_con(
        (None, 7, Decimal("1000.00"), "Pagada", "ARS"),
        (Decimal("1000.00"),),
    )
    with pytest.raises(ValueError, match="ya está pagada"):
        pago(cursor, "1")


def test_pago_sobre_factura_anulada_rechazado():
    cursor = cursor_con((None, 7, Decimal("1000.00"), "Anulada", "ARS"))
    with pytest.raises(ValueError, match="anulada"):
        pago(cursor, "1")


def test_pago_a_titular_inactivo_permitido():
    # El pago no consulta el estado del titular: la deuda se puede pagar.
    cursor = cursor_con(
        (None, 7, Decimal("1000.00"), "Pendiente", "ARS"),
        (Decimal("0"),),
        (10, "ARS"),
        (33, date(2026, 10, 30)),
    )
    pago(cursor, "1000")
    assert not any("FROM operador_logistico" in s or "FROM proveedor" in s
                   for s in sqls(cursor))


def test_pago_sin_metodo_rechazado():
    cursor = cursor_con()
    with pytest.raises(ValueError, match="método"):
        ejecutar(cursor, repo.registrar_pago_emitido, 5, 10, "  ")


# ------------------------------------------------------------ consultas

def test_vencimientos_usa_ventana_de_dias():
    cursor = MagicMock()
    cursor.fetchall.return_value = []
    ejecutar(cursor, repo.listar_vencimientos, 7, hoy=HOY)
    sql, params = cursor.execute.call_args.args
    assert "fecha_vencimiento <= %s" in sql
    assert "estado IN ('Pendiente', 'Parcial')" in sql
    assert params == (HOY, date(2026, 11, 6))


def test_vencimientos_dias_negativos_rechazados():
    with pytest.raises(ValueError):
        repo.listar_vencimientos(-1, hoy=HOY)


def test_consultar_cuenta_inexistente_devuelve_none():
    cursor = cursor_con(None)
    assert ejecutar(cursor, repo.consultar_cuenta_tercero, "PROVEEDOR", 1) is None


def test_tramos_facturables_exige_entregado_y_sin_factura():
    cursor = MagicMock()
    cursor.fetchall.return_value = []
    ejecutar(cursor, repo.listar_tramos_facturables, 7)
    sql = cursor.execute.call_args.args[0]
    assert "LOWER(e.estado) = 'entregado'" in sql
    assert "e.fecha_entrega IS NOT NULL" in sql
    assert "NOT EXISTS" in sql
