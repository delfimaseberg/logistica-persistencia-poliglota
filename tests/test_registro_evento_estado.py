"""Registro de eventos que cambian el estado: guarda el evento (MongoDB) y el estado (PostgreSQL) juntos.

registrar_evento_y_estado deja las dos bases juntas o ninguna:
si MongoDB falla, PostgreSQL hace rollback;
si el commit de PostgreSQL falla, se borra el evento de MongoDB;
si el UPDATE del envío no afecta filas, MongoDB no se toca.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.repositories import trazabilidad_repository as traz_repo
from app.services import trazabilidad_service


ENTREGA = datetime(2026, 10, 20, 15, 30, tzinfo=timezone.utc)
DOCUMENTO = {"envio_id": 45, "tipo": "ENTREGADO", "fecha_hora": ENTREGA}


class ConexionFalsa:
    """Imita el with de psycopg: commit si no hubo error, rollback si lo hubo."""

    def __init__(self, filas_afectadas=1, falla_commit=False):
        self.cursor_falso = MagicMock()
        self.cursor_falso.rowcount = filas_afectadas
        self.falla_commit = falla_commit
        self.commits = 0
        self.rollbacks = 0

    def __enter__(self):
        return self

    def __exit__(self, tipo_error, _valor, _traza):
        if tipo_error is None:
            self.commits += 1
            if self.falla_commit:
                raise RuntimeError("se cortó la conexión en el commit")
        else:
            self.rollbacks += 1
        return False

    def cursor(self):
        contexto = MagicMock()
        contexto.__enter__.return_value = self.cursor_falso
        return contexto


def ejecutar(conexion, insertar=None, eliminar=None, estado="Entregado"):
    insertar = insertar or MagicMock(return_value="evento-1")
    eliminar = eliminar or MagicMock(return_value=True)
    with patch.object(traz_repo, "get_postgres_connection", return_value=conexion), \
         patch.object(traz_repo, "insertar_evento", insertar), \
         patch.object(traz_repo, "eliminar_evento", eliminar):
        resultado = traz_repo.registrar_evento_y_estado(DOCUMENTO, 45, estado, ENTREGA)
    return resultado, insertar, eliminar


# repo

def test_caso_normal_hace_commit_y_guarda_el_evento():
    conexion = ConexionFalsa()
    resultado, insertar, eliminar = ejecutar(conexion)

    assert resultado == "evento-1"
    insertar.assert_called_once_with(DOCUMENTO)
    assert (conexion.commits, conexion.rollbacks) == (1, 0)
    eliminar.assert_not_called()
    # Mismos UPDATE que actualizar_estado_envio: envío y sensores.
    sentencias = [c.args[0] for c in conexion.cursor_falso.execute.call_args_list]
    assert "UPDATE envio" in sentencias[0]
    assert "UPDATE sensor_iot" in sentencias[1]
    assert conexion.cursor_falso.execute.call_args_list[0].args[1] == ("Entregado", ENTREGA, 45)


def test_si_falla_mongodb_postgresql_hace_rollback_y_no_queda_nada():
    conexion = ConexionFalsa()
    insertar = MagicMock(side_effect=RuntimeError("MongoDB no responde"))

    with pytest.raises(RuntimeError, match="MongoDB no responde"):
        ejecutar(conexion, insertar=insertar)

    assert (conexion.commits, conexion.rollbacks) == (0, 1)


def test_si_falla_el_commit_se_borra_el_evento_de_mongodb():
    conexion = ConexionFalsa(falla_commit=True)
    eliminar = MagicMock(return_value=True)

    with pytest.raises(RuntimeError, match="commit"):
        ejecutar(conexion, eliminar=eliminar)

    assert conexion.commits == 1
    eliminar.assert_called_once_with("evento-1")


def test_si_la_compensacion_tambien_falla_se_informa_el_error_original():
    conexion = ConexionFalsa(falla_commit=True)
    eliminar = MagicMock(side_effect=RuntimeError("MongoDB caído"))

    with pytest.raises(RuntimeError, match="commit"):
        ejecutar(conexion, eliminar=eliminar)
    eliminar.assert_called_once_with("evento-1")


def test_update_sin_filas_no_toca_mongodb():
    conexion = ConexionFalsa(filas_afectadas=0)
    insertar = MagicMock()

    with pytest.raises(traz_repo.EstadoNoActualizado):
        ejecutar(conexion, insertar=insertar)

    insertar.assert_not_called()
    assert (conexion.commits, conexion.rollbacks) == (0, 1)
    assert conexion.cursor_falso.execute.call_count == 1   # no apaga sensores


def test_entregado_sin_fecha_se_rechaza_antes_de_abrir_la_transaccion():
    abrir = MagicMock()
    with patch.object(traz_repo, "get_postgres_connection", abrir), \
         pytest.raises(ValueError, match="fecha real de entrega"):
        traz_repo.registrar_evento_y_estado(DOCUMENTO, 45, "Entregado", None)
    abrir.assert_not_called()


# servicio

ENVIO = (45, 7, "Cliente", "A", "B", "En tránsito", "Media",
         datetime(2026, 10, 1, tzinfo=timezone.utc), None)


def registrar_evento(monkeypatch, tipo, nuevo_estado):
    """Corre registrar_evento_service sin consola ni bases."""
    monkeypatch.setattr(trazabilidad_service, "pedir_envio", lambda: ENVIO)
    monkeypatch.setattr(trazabilidad_service, "elegir_tipo_evento", lambda: tipo)
    monkeypatch.setattr(trazabilidad_service, "tipos_registrados", lambda _id: set())
    monkeypatch.setattr(trazabilidad_service, "validar_evento_permitido", lambda *_a: [])
    monkeypatch.setattr(trazabilidad_service, "pedir_detalle", lambda _tipo: {})
    monkeypatch.setattr(trazabilidad_service, "obtener_sesion_actual", lambda: None)
    monkeypatch.setattr(trazabilidad_service, "pausar", lambda: None)
    monkeypatch.setattr(trazabilidad_service, "estado_nuevo_por_evento", lambda *_a: nuevo_estado)
    monkeypatch.setattr("builtins.input", lambda *_a: "S")

    def pedir(mensaje, _validador, *_args):
        if mensaje.startswith("Fecha"):
            return ENTREGA
        if mensaje.startswith(("Ubicación", "Descripción")):
            return "texto"
        return None

    monkeypatch.setattr(trazabilidad_service, "pedir", pedir)
    trazabilidad_service.registrar_evento_service()


def test_servicio_guarda_evento_y_estado_juntos_cuando_cambia_el_estado(monkeypatch, capsys):
    transaccion = MagicMock(return_value="evento-1")
    insertar, sincronizar, pendiente = MagicMock(), MagicMock(), MagicMock()
    monkeypatch.setattr(trazabilidad_service, "registrar_evento_y_estado", transaccion)
    monkeypatch.setattr(trazabilidad_service, "insertar_evento", insertar)
    monkeypatch.setattr(trazabilidad_service, "sincronizar_envio_neo4j", sincronizar)
    monkeypatch.setattr(trazabilidad_service, "registrar_pendiente_estado", pendiente)

    registrar_evento(monkeypatch, "ENTREGADO", "Entregado")

    documento, id_envio, estado, fecha = transaccion.call_args.args
    assert (documento["tipo"], id_envio, estado, fecha) == ("ENTREGADO", 45, "Entregado", ENTREGA)
    insertar.assert_not_called()
    sincronizar.assert_called_once_with(45)
    pendiente.assert_not_called()
    salida = capsys.readouterr().out
    assert "Evento registrado correctamente." in salida
    assert "Fecha real de entrega registrada" in salida
    assert "Estado del envío actualizado a: Entregado" in salida


def test_servicio_si_falla_el_guardado_conjunto_no_deja_pendiente(monkeypatch, capsys):
    transaccion = MagicMock(side_effect=RuntimeError("MongoDB no responde"))
    sincronizar, pendiente = MagicMock(), MagicMock()
    monkeypatch.setattr(trazabilidad_service, "registrar_evento_y_estado", transaccion)
    monkeypatch.setattr(trazabilidad_service, "sincronizar_envio_neo4j", sincronizar)
    monkeypatch.setattr(trazabilidad_service, "registrar_pendiente_estado", pendiente)

    registrar_evento(monkeypatch, "ENTREGADO", "Entregado")

    pendiente.assert_not_called()
    sincronizar.assert_not_called()
    salida = capsys.readouterr().out
    assert "No se registró el evento: MongoDB no responde" in salida
    assert "Evento registrado correctamente." not in salida


def test_servicio_evento_sin_cambio_de_estado_sigue_igual(monkeypatch, capsys):
    transaccion = MagicMock()
    insertar = MagicMock(return_value="evento-2")
    sincronizar = MagicMock()
    monkeypatch.setattr(trazabilidad_service, "registrar_evento_y_estado", transaccion)
    monkeypatch.setattr(trazabilidad_service, "insertar_evento", insertar)
    monkeypatch.setattr(trazabilidad_service, "sincronizar_envio_neo4j", sincronizar)

    registrar_evento(monkeypatch, "INSPECCION", None)

    insertar.assert_called_once()
    transaccion.assert_not_called()
    sincronizar.assert_not_called()
    assert "Evento registrado correctamente." in capsys.readouterr().out
