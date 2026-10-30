"""Sesión compartida de Cassandra: una conexión por proceso, no por operación."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.database import cassandra_connection as conexion
from app.repositories import lectura_iot_repository as repo


@pytest.fixture
def cluster_falso(monkeypatch):
    """Reemplaza Cluster y deja la sesión compartida vacía antes y después."""
    conexion._cluster = conexion._session = None
    repo._preparadas.clear()
    fabrica = MagicMock()
    sesion = fabrica.return_value.connect.return_value
    sesion.is_shutdown = False
    monkeypatch.setattr(conexion, "Cluster", fabrica)
    yield fabrica, sesion
    conexion._cluster = conexion._session = None
    repo._preparadas.clear()


def test_la_sesion_se_crea_una_vez_y_se_reutiliza(cluster_falso):
    fabrica, sesion = cluster_falso
    assert conexion.obtener_sesion_cassandra() is sesion
    assert conexion.obtener_sesion_cassandra() is sesion
    fabrica.assert_called_once()
    fabrica.return_value.connect.assert_called_once_with(conexion.CASSANDRA_KEYSPACE)


def test_cien_lecturas_usan_una_sola_conexion_y_preparan_una_vez(cluster_falso):
    fabrica, sesion = cluster_falso
    for i in range(100):
        repo.registrar_lectura_db(7, 3, temperatura=4.0 + i / 100)
        repo.consultar_ultima_lectura_db(7)

    fabrica.assert_called_once()                    # una conexión para todo
    assert sesion.prepare.call_count == 4           # 3 INSERT + 1 SELECT, una vez
    assert sesion.execute.call_count == 200
    sesion.shutdown.assert_not_called()             # no se cierra por operación


def test_cerrar_conexion_no_cierra_la_sesion_compartida(cluster_falso):
    _, sesion = cluster_falso
    cluster, s = repo.abrir_conexion()
    repo.cerrar_conexion(cluster, s)
    assert cluster is None
    sesion.shutdown.assert_not_called()


def test_cerrar_conexion_si_cierra_conexiones_propias():
    cluster, sesion = MagicMock(), MagicMock()
    repo.cerrar_conexion(cluster, sesion)
    sesion.shutdown.assert_called_once()
    cluster.shutdown.assert_called_once()


def test_cierre_al_salir_y_reconexion(cluster_falso):
    fabrica, sesion = cluster_falso
    conexion.obtener_sesion_cassandra()
    conexion.cerrar_sesion_cassandra()
    fabrica.return_value.shutdown.assert_called_once()
    conexion.obtener_sesion_cassandra()
    assert fabrica.call_count == 2


def test_sesion_cerrada_se_vuelve_a_crear(cluster_falso):
    fabrica, sesion = cluster_falso
    conexion.obtener_sesion_cassandra()
    sesion.is_shutdown = True
    conexion.obtener_sesion_cassandra()
    assert fabrica.call_count == 2


def test_el_cierre_esta_registrado_para_la_salida_del_proceso():
    with patch("atexit.register") as registrar:
        import importlib
        importlib.reload(conexion)
    registrar.assert_called_once_with(conexion.cerrar_sesion_cassandra)


def test_lectura_historica_va_a_la_particion_de_su_mes(cluster_falso, monkeypatch):
    batch = MagicMock()
    monkeypatch.setattr(repo, "BatchStatement", MagicMock(return_value=batch))
    momento = datetime(2026, 8, 5, 12, tzinfo=timezone.utc)
    repo.registrar_lectura_db(7, 3, humedad=50.0, fecha_hora=momento)
    sensor, contenedor, ultima = [c.args[1] for c in batch.add.call_args_list]
    assert sensor[:3] == (7, "2026-08", momento)
    assert contenedor[:3] == (3, "2026-08", momento)
    assert ultima[:3] == (7, 3, momento)


def test_lectura_sin_zona_horaria_se_rechaza(cluster_falso):
    with pytest.raises(ValueError, match="zona horaria"):
        repo.registrar_lectura_db(7, 3, fecha_hora=datetime(2026, 8, 5, 12))


def test_existe_lectura_consulta_por_clave_completa(cluster_falso):
    _, sesion = cluster_falso
    sesion.execute.return_value.one.return_value = object()
    momento = datetime(2026, 9, 2, 11, 0, tzinfo=timezone.utc)
    assert repo.existe_lectura_sensor(7, momento) is True
    cql = sesion.prepare.call_args.args[0]
    assert "sensor_id = ?" in cql and "anio_mes = ?" in cql and "fecha_hora = ?" in cql
    assert sesion.execute.call_args.args[1] == (7, "2026-09", momento)

    sesion.execute.return_value.one.return_value = None
    assert repo.existe_lectura_sensor(7, momento) is False
