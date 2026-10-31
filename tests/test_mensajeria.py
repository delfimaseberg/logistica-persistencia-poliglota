from unittest.mock import MagicMock, patch

import pytest

from app.repositories import mensajeria_repository as repo
from app.services import mensajeria_service as servicio


def test_mensaje_privado_guarda_remitente_y_destinatario():
    coleccion = MagicMock()
    coleccion.insert_one.return_value.inserted_id = "mensaje-1"

    with patch.object(
        repo, "coleccion_mensajes", return_value=coleccion
    ):
        resultado = repo.registrar_mensaje_privado(
            1, 2, "Hola"
        )

    documento = coleccion.insert_one.call_args.args[0]

    assert resultado == "mensaje-1"
    assert documento["tipo"] == "Privado"
    assert documento["remitente_id"] == 1
    assert documento["destinatario_id"] == 2
    assert documento["contenido"] == "Hola"
    assert documento["leido"] is False


def test_bandeja_filtra_por_destinatario():
    coleccion = MagicMock()
    coleccion.find.return_value.sort.return_value.limit.return_value = []

    with patch.object(
        repo, "coleccion_mensajes", return_value=coleccion
    ):
        repo.obtener_bandeja_entrada(2)

    filtro = coleccion.find.call_args.args[0]

    # La bandeja incluye los mensajes privados y los de alertas.
    assert filtro == {
        "tipo": {"$in": ["Privado", "Alerta"]},
        "destinatario_id": 2
    }


def test_conversacion_incluye_ambas_direcciones():
    coleccion = MagicMock()
    coleccion.find.return_value.sort.return_value.limit.return_value = []

    with patch.object(
        repo, "coleccion_mensajes", return_value=coleccion
    ):
        repo.obtener_conversacion(1, 2)

    filtro = coleccion.find.call_args.args[0]

    assert filtro["tipo"] == "Privado"
    assert len(filtro["$or"]) == 2
    assert {
        "remitente_id": 1,
        "destinatario_id": 2
    } in filtro["$or"]
    assert {
        "remitente_id": 2,
        "destinatario_id": 1
    } in filtro["$or"]


def test_no_se_puede_marcar_mensaje_ajeno_como_leido():
    coleccion = MagicMock()
    coleccion.update_one.return_value.matched_count = 0

    with patch.object(
        repo, "coleccion_mensajes", return_value=coleccion
    ):
        resultado = repo.marcar_mensaje_leido(
            "507f1f77bcf86cd799439011", 99
        )

    assert resultado is False

    filtro = coleccion.update_one.call_args.args[0]
    assert filtro["destinatario_id"] == 99


def test_id_invalido_no_modifica_mensajes():
    coleccion = MagicMock()

    with patch.object(
        repo, "coleccion_mensajes", return_value=coleccion
    ):
        resultado = repo.marcar_mensaje_leido(
            "id-invalido", 1
        )

    assert resultado is False
    coleccion.update_one.assert_not_called()


def test_creador_del_grupo_es_administrador():
    coleccion = MagicMock()
    coleccion.insert_one.return_value.inserted_id = "grupo-1"

    with patch.object(
        repo, "coleccion_grupos", return_value=coleccion
    ):
        resultado = repo.crear_grupo(
            "Logística", "Equipo de operaciones", 1
        )

    documento = coleccion.insert_one.call_args.args[0]

    assert resultado == "grupo-1"
    assert documento["creador_id"] == 1
    assert documento["miembros"][0]["usuario_id"] == 1
    assert documento["miembros"][0]["rol"] == "Administrador"


def test_usuario_es_miembro_del_grupo():
    grupo = {
        "miembros": [
            {"usuario_id": 1},
            {"usuario_id": 2}
        ]
    }

    assert repo.usuario_es_miembro(grupo, 1) is True
    assert repo.usuario_es_miembro(grupo, 3) is False


def test_no_se_puede_enviar_mensaje_a_grupo_ajeno():
    grupo = {
        "_id": "grupo-1",
        "miembros": [{"usuario_id": 1}]
    }

    with patch.object(
        repo, "buscar_grupo", return_value=grupo
    ), patch.object(
        repo, "coleccion_mensajes"
    ) as coleccion:
        with pytest.raises(PermissionError):
            repo.registrar_mensaje_grupo(
                2, "grupo-1", "Mensaje no autorizado"
            )

    coleccion.assert_not_called()


def test_no_se_puede_consultar_grupo_ajeno():
    grupo = {
        "_id": "grupo-1",
        "miembros": [{"usuario_id": 1}]
    }

    with patch.object(
        repo, "buscar_grupo", return_value=grupo
    ):
        with pytest.raises(PermissionError):
            repo.obtener_mensajes_grupo("grupo-1", 2)


def test_sesion_obligatoria_para_mensajeria():
    with patch.object(
        servicio, "obtener_sesion_actual", return_value=None
    ):
        with pytest.raises(PermissionError):
            servicio.obtener_id_usuario_actual()


def test_sesion_identifica_al_remitente():
    sesion = {"id_usuario": 5}

    with patch.object(
        servicio, "obtener_sesion_actual", return_value=sesion
    ):
        resultado = servicio.obtener_id_usuario_actual()

    assert resultado == 5