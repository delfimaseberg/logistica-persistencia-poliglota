"""Tarifa estándar: precios por medio sobre el motor de reglas."""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from app.repositories import precios_repository as repo


PRECIOS = {"Terrestre": "5000", "Marítimo": "20000", "Aéreo": "40000.50"}


def crear_conexion_mock(cursor):
    conexion = MagicMock()
    conexion.__enter__.return_value = conexion
    conexion.cursor.return_value.__enter__.return_value = cursor
    return conexion


def test_validar_precios_normaliza():
    base, precios = repo.validar_precios("0", PRECIOS)
    assert base == Decimal("0")
    assert precios["Aéreo"] == Decimal("40000.50")


@pytest.mark.parametrize("base, precios, texto", [
    ("-1", PRECIOS, "negativo"),
    ("10", {**PRECIOS, "Terrestre": "0"}, "mayor a cero"),
    ("10", {k: v for k, v in PRECIOS.items() if k != "Aéreo"}, "Aéreo"),
    ("10.001", PRECIOS, "2 decimales"),
    ("abc", PRECIOS, "inválido"),
])
def test_validar_precios_rechaza(base, precios, texto):
    with pytest.raises(ValueError, match=texto):
        repo.validar_precios(base, precios)


def definir(cursor, **kwargs):
    with patch.object(repo, "get_postgres_connection",
                      return_value=crear_conexion_mock(cursor)):
        return repo.definir_tarifa_estandar(
            kwargs.get("base", "1000"), PRECIOS, 4, kwargs.get("ref", "lista 11/2026"))


def test_definir_crea_version_aprobada_y_reemplaza_la_anterior():
    cursor = MagicMock()
    cursor.fetchone.side_effect = [(3,), (50,), (49,)]
    # versión siguiente, id de la nueva regla, anterior aprobada
    assert definir(cursor) == 50

    sqls = [c.args[0] for c in cursor.execute.call_args_list]
    params = [c.args[1] if len(c.args) > 1 else None for c in cursor.execute.call_args_list]

    insert_regla = next(i for i, s in enumerate(sqls) if "INSERT INTO regla_tarifaria_version" in s)
    assert params[insert_regla][0:3] == ("TARIFA_ESTANDAR", 3, "ARS")

    componentes = [p for s, p in zip(sqls, params) if "INSERT INTO regla_tarifaria_componente" in s]
    assert [(p[1], p[2], p[4], p[5]) for p in componentes] == [
        ("BASE", None, "FIJO", Decimal("1000")),
        ("TRANSPORTE", "Terrestre", "FIJO", Decimal("5000")),
        ("TRANSPORTE", "Marítimo", "FIJO", Decimal("20000")),
        ("TRANSPORTE", "Aéreo", "FIJO", Decimal("40000.50")),
    ]

    # Auditoría en la misma transacción antes de cada cambio de estado.
    i_aud_reemplazo = next(i for i, s in enumerate(sqls) if "'APROBADA', 'REEMPLAZADA'" in s)
    i_reemplazo = next(i for i, s in enumerate(sqls) if "SET estado = 'REEMPLAZADA'" in s)
    i_aud_aprob = next(i for i, s in enumerate(sqls) if "'BORRADOR', 'APROBADA'" in s)
    i_aprob = next(i for i, s in enumerate(sqls) if "SET estado = 'APROBADA'" in s)
    assert i_aud_reemplazo < i_reemplazo < i_aud_aprob < i_aprob
    assert params[i_reemplazo] == (49,)
    assert params[i_aprob] == ("lista 11/2026", 4, 50)


def test_primera_version_no_reemplaza_nada():
    cursor = MagicMock()
    cursor.fetchone.side_effect = [(1,), (50,), None]
    definir(cursor)
    assert not any("REEMPLAZADA'" in c.args[0] and "UPDATE" in c.args[0]
                   for c in cursor.execute.call_args_list)


def test_definir_exige_referencia():
    cursor = MagicMock()
    with pytest.raises(ValueError, match="referencia"):
        definir(cursor, ref="  ")
    cursor.execute.assert_not_called()


def test_obtener_tarifa_estandar_arma_precios_por_medio():
    cursor = MagicMock()
    cursor.fetchone.return_value = (50, 3, None, None, "lista")
    cursor.fetchall.return_value = [
        ("BASE", None, Decimal("1000")),
        ("TRANSPORTE", "Aéreo", Decimal("40000")),
        ("TRANSPORTE", "Terrestre", Decimal("5000")),
    ]
    with patch.object(repo, "get_postgres_connection",
                      return_value=crear_conexion_mock(cursor)):
        tarifa = repo.obtener_tarifa_estandar()
    assert tarifa["base"] == Decimal("1000")
    assert tarifa["precios"] == {"Aéreo": Decimal("40000"), "Terrestre": Decimal("5000")}
