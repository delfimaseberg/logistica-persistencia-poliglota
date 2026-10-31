"""Fecha real de entrega: solo con el evento ENTREGADO; Entregado es final."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.repositories import trazabilidad_repository as traz_repo
from app.services import envio_service
from app.services import trazabilidad_service


ENTREGA = datetime(2026, 10, 20, 15, 30, tzinfo=timezone.utc)


def crear_conexion_mock(cursor):
    conexion = MagicMock()
    conexion.__enter__.return_value = conexion
    conexion.cursor.return_value.__enter__.return_value = cursor
    return conexion


def actualizar(*args):
    cursor = MagicMock()
    cursor.rowcount = 1
    with patch.object(traz_repo, "get_postgres_connection",
                      return_value=crear_conexion_mock(cursor)):
        resultado = traz_repo.actualizar_estado_envio(*args)
    return resultado, cursor


def test_entregado_guarda_la_fecha_real_de_entrega():
    resultado, cursor = actualizar(45, "Entregado", ENTREGA)
    # Primera sentencia: estado y fecha; la segunda apaga los sensores.
    sql, params = cursor.execute.call_args_list[0].args
    assert resultado is True
    assert "fecha_entrega = %s" in sql
    assert params == ("Entregado", ENTREGA, 45)


def test_entregado_pasa_los_sensores_del_envio_a_inactivo():
    _, cursor = actualizar(45, "Entregado", ENTREGA)
    assert cursor.execute.call_count == 2
    sql, params = cursor.execute.call_args_list[1].args
    assert "UPDATE sensor_iot" in sql
    assert "estado = 'Inactivo'" in sql
    assert "motivo_inactivo = 'Entrega del envío '" in sql
    assert "s.estado = 'Activo'" in sql
    assert params == (45, 45)


def test_otro_estado_no_toca_los_sensores():
    _, cursor = actualizar(45, "En tránsito", ENTREGA)
    assert cursor.execute.call_count == 1


def test_si_el_envio_ya_estaba_entregado_no_toca_los_sensores():
    cursor = MagicMock()
    cursor.rowcount = 0
    with patch.object(traz_repo, "get_postgres_connection",
                      return_value=crear_conexion_mock(cursor)):
        assert traz_repo.actualizar_estado_envio(45, "Entregado", ENTREGA) is False
    assert cursor.execute.call_count == 1


def test_entregado_sin_fecha_se_rechaza():
    with pytest.raises(ValueError, match="fecha real de entrega"):
        actualizar(45, "Entregado")


def test_otros_estados_no_guardan_fecha_y_entregado_es_final():
    _, cursor = actualizar(45, "En tránsito", ENTREGA)
    sql, params = cursor.execute.call_args.args
    assert params == ("En tránsito", None, 45)
    assert "LOWER(BTRIM(estado)) <> 'entregado'" in sql


def test_pendiente_de_estado_usa_su_fecha_guardada():
    pendiente = {"envio_id": 45, "estado": "Entregado",
                 "fecha_entrega": ENTREGA, "evento_id": "e1"}
    assert trazabilidad_service.fecha_entrega_de_pendiente(pendiente) == ENTREGA
    assert trazabilidad_service.fecha_entrega_de_pendiente(
        {"envio_id": 45, "estado": "En tránsito"}) is None


def test_pendiente_viejo_toma_la_fecha_del_evento_entregado(monkeypatch):
    monkeypatch.setattr(trazabilidad_service, "listar_eventos_envio", lambda _id: [
        {"_id": "otro", "fecha_hora": datetime(2026, 1, 1, tzinfo=timezone.utc)},
        {"_id": "e1", "fecha_hora": ENTREGA},
    ])
    pendiente = {"envio_id": 45, "estado": "Entregado", "evento_id": "e1"}
    assert trazabilidad_service.fecha_entrega_de_pendiente(pendiente) == ENTREGA

    monkeypatch.setattr(trazabilidad_service, "listar_eventos_envio", lambda _id: [])
    with pytest.raises(ValueError, match="evento ENTREGADO"):
        trazabilidad_service.fecha_entrega_de_pendiente(pendiente)


# -------------------------------------------------- "Modificar envío"

ENVIO_ENTREGADO = (45, 7, "Cliente", "A", "B", "Entregado", "Media",
                   datetime(2026, 10, 1, tzinfo=timezone.utc), ENTREGA)
ENVIO_EN_TRANSITO = (46, 7, "Cliente", "A", "B", "En tránsito", "Media",
                     datetime(2026, 10, 1, tzinfo=timezone.utc), None)


def test_entregado_no_se_elige_a_mano():
    assert "Entregado" not in envio_service.ESTADOS_EDITABLES
    with pytest.raises(ValueError):
        from app.utils.validaciones import validar_opcion
        validar_opcion("Entregado", envio_service.ESTADOS_EDITABLES, "El estado")


@pytest.mark.parametrize("opcion", ["1", "2", "3", "4"])
def test_envio_entregado_no_cambia_cliente_ruta_ni_estado(opcion, capsys):
    actualizar_envio = MagicMock()
    with patch.object(envio_service, "buscar_envio_por_id", return_value=ENVIO_ENTREGADO), \
         patch.object(envio_service, "actualizar_envio", actualizar_envio), \
         patch("builtins.input", side_effect=["45", opcion, ""]):
        envio_service.modificar_envio_service()
    actualizar_envio.assert_not_called()
    assert "Entregado" in capsys.readouterr().out


def test_envio_entregado_no_se_elimina(capsys):
    eliminar = MagicMock()
    with patch.object(envio_service, "buscar_envio_por_id", return_value=ENVIO_ENTREGADO), \
         patch.object(envio_service, "eliminar_envio_db", eliminar), \
         patch("builtins.input", side_effect=["45", ""]):
        envio_service.eliminar_envio_service()
    eliminar.assert_not_called()


def test_mostrar_envio_incluye_la_fecha_de_entrega(capsys):
    envio_service.mostrar_envio(ENVIO_ENTREGADO)
    assert "Fecha real de entrega" in capsys.readouterr().out
    envio_service.mostrar_envio(ENVIO_EN_TRANSITO)
    assert "Fecha real de entrega" not in capsys.readouterr().out
