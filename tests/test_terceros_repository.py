from unittest.mock import MagicMock, patch

import pytest
from psycopg import errors

from app.repositories import terceros_repository as repo


def crear_conexion_mock(cursor):
    conexion = MagicMock()
    conexion.__enter__.return_value = conexion
    conexion.cursor.return_value.__enter__.return_value = cursor
    return conexion


def ejecutar(cursor, funcion, *args):
    with patch.object(
        repo, "get_postgres_connection",
        return_value=crear_conexion_mock(cursor),
    ):
        return funcion(*args)


DATOS_OPERADOR = {
    "razon_social": "Naviera del Plata S.A.",
    "cuit": "30-71234567-1",
    "email": "ops@naviera.example",
    "telefono": None,
    "direccion": None,
    "pais": "Argentina",
    "modalidades": ["Marítimo"],
}


def test_alta_operador_queda_activo():
    cursor = MagicMock()
    cursor.fetchone.return_value = (1,)
    assert ejecutar(cursor, repo.crear_operador, DATOS_OPERADOR) == 1
    sql, params = cursor.execute.call_args.args
    assert "INSERT INTO operador_logistico" in sql
    assert "'ACTIVO'" in sql
    assert params[6] == ["Marítimo"]


def test_cuit_duplicado_se_informa():
    cursor = MagicMock()
    cursor.execute.side_effect = errors.UniqueViolation("duplicado")
    with pytest.raises(ValueError, match="CUIT"):
        ejecutar(cursor, repo.crear_proveedor, {
            **DATOS_OPERADOR, "rubro": "SEGUROS",
        })


@pytest.mark.parametrize("funcion, tabla", [
    (repo.dar_de_baja_proveedor, "proveedor"),
    (repo.dar_de_baja_operador, "operador_logistico"),
])
def test_baja_es_logica(funcion, tabla):
    cursor = MagicMock()
    cursor.rowcount = 1
    assert ejecutar(cursor, funcion, 3) is True
    sql = cursor.execute.call_args.args[0]
    assert "DELETE" not in sql.upper()
    assert f"UPDATE {tabla}" in sql
    assert "estado = 'INACTIVO'" in sql
    assert "fecha_baja = CURRENT_TIMESTAMP" in sql


def test_reactivar_limpia_fecha_de_baja():
    cursor = MagicMock()
    cursor.rowcount = 1
    ejecutar(cursor, repo.reactivar_operador, 3)
    sql = cursor.execute.call_args.args[0]
    assert "estado = 'ACTIVO'" in sql and "fecha_baja = NULL" in sql


def test_operadores_por_modalidad_solo_activos():
    cursor = MagicMock()
    cursor.fetchall.return_value = []
    ejecutar(cursor, repo.listar_operadores_por_modalidad, "Aéreo")
    sql, params = cursor.execute.call_args.args
    assert "estado = 'ACTIVO'" in sql
    assert "= ANY (modalidades)" in sql
    assert params == ("Aéreo",)


# ------------------------------------------------- asignaciones de operador

def cursor_con(*respuestas, rowcount=1):
    cursor = MagicMock()
    cursor.fetchone.side_effect = list(respuestas)
    cursor.rowcount = rowcount
    return cursor


def test_asignar_operador_tramo_ok_devuelve_envio():
    cursor = cursor_con((4, "Marítimo", None), ("ACTIVO", ["Marítimo"]))
    assert ejecutar(cursor, repo.asignar_operador_tramo, 3, 2) == 4


def test_asignar_operador_tramo_no_reemplaza():
    cursor = cursor_con((4, "Marítimo", 9))
    with pytest.raises(ValueError, match="ya tiene"):
        ejecutar(cursor, repo.asignar_operador_tramo, 3, 2)


def test_asignar_operador_tramo_exige_modalidad():
    cursor = cursor_con((4, "Aéreo", None), ("ACTIVO", ["Terrestre"]))
    with pytest.raises(ValueError, match="modalidad"):
        ejecutar(cursor, repo.asignar_operador_tramo, 3, 2)


def test_asignar_operador_tramo_inactivo():
    cursor = cursor_con((4, "Terrestre", None), ("INACTIVO", ["Terrestre"]))
    with pytest.raises(ValueError, match="inactivo"):
        ejecutar(cursor, repo.asignar_operador_tramo, 3, 2)


def test_asignar_operador_vehiculo_exige_modalidad():
    cursor = cursor_con(("Terrestre",), ("ACTIVO", ["Marítimo"]))
    with pytest.raises(ValueError, match="modalidad"):
        ejecutar(cursor, repo.asignar_operador_vehiculo, 1, 2)


def test_quitar_operador_de_vehiculo():
    cursor = cursor_con(("Terrestre",))
    assert ejecutar(cursor, repo.asignar_operador_vehiculo, 1, None) is True
    assert cursor.execute.call_args.args[1] == (None, 1)


def test_tipo_invalido():
    with pytest.raises(ValueError):
        repo._config("CLIENTE")
