from datetime import datetime, timezone

import pytest

pytestmark = pytest.mark.integration


def test_trazabilidad_mongo_postgres_neo4j(synthetic_logistics, monkeypatch):
    from app.services import trazabilidad_service
    from app.repositories.evento_repository import listar_eventos_envio
    from app.repositories.grafo_repository import obtener_ruta_envio
    from app.repositories.trazabilidad_repository import actualizar_estado_envio
    from app.services.sincronizacion_service import sincronizar_envio_neo4j
    from app.database.postgres_connection import get_postgres_connection

    data = synthetic_logistics
    row = (
        data["shipment_id"], data["client_id"], f"Cliente {data['token']}",
        "Origen", "Destino", "Pendiente", "Alta", datetime.now(timezone.utc),
    )
    monkeypatch.setattr(trazabilidad_service, "pedir_envio", lambda: row)
    monkeypatch.setattr(trazabilidad_service, "elegir_tipo_evento", lambda: "EN_TRANSITO")
    monkeypatch.setattr(trazabilidad_service, "tipos_registrados", lambda _id: set())
    monkeypatch.setattr(trazabilidad_service, "pedir_detalle", lambda _tipo: {})
    monkeypatch.setattr(trazabilidad_service, "obtener_sesion_actual", lambda: None)
    monkeypatch.setattr(trazabilidad_service, "pausar", lambda: None)
    monkeypatch.setattr(trazabilidad_service, "input", lambda *_args: "S", raising=False)

    def pedir(mensaje, _validador, *_args):
        if mensaje.startswith("Fecha"):
            return datetime.now(timezone.utc)
        if mensaje.startswith("Ubicación"):
            return "Centro de prueba"
        if mensaje.startswith("Descripción"):
            return "Evento sintético de integración"
        return None

    monkeypatch.setattr(trazabilidad_service, "pedir", pedir)
    trazabilidad_service.registrar_evento_service()

    events = listar_eventos_envio(data["shipment_id"])
    assert len(events) == 1
    assert events[0]["tipo"] == "EN_TRANSITO"

    with get_postgres_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT estado FROM envio WHERE id_envio=%s", (data["shipment_id"],))
            assert cursor.fetchone()[0] == "En tránsito"

    assert sincronizar_envio_neo4j(data["shipment_id"]) is True
    route = obtener_ruta_envio(data["shipment_id"])
    assert route and route[0]["estado"] == "En tránsito"
    assert route[0]["id_tramo"] is not None


def test_iot_anomalia_alerta_mongo_e_incidente_postgres(synthetic_logistics, monkeypatch):
    from app.services import incidentes_service
    from app.repositories.lectura_iot_repository import (
        registrar_lectura_db,
        consultar_ultima_lectura_db,
    )
    from app.database.mongo_connection import get_mongo_database
    from app.database.postgres_connection import get_postgres_connection

    data = synthetic_logistics
    lectura_id = registrar_lectura_db(
        id_sensor=data["sensor_id"],
        id_contenedor=data["container_id"],
        temperatura=9.0,
        bateria=80.0,
    )
    assert consultar_ultima_lectura_db(data["sensor_id"]).id_lectura == lectura_id

    monkeypatch.setattr(incidentes_service, "input", lambda *_args: "S", raising=False)
    monkeypatch.setattr(incidentes_service, "pausar", lambda: None)
    incidentes_service.detectar_alertas_service()

    alerts = list(get_mongo_database()["alertas"].find({"sensor_id": data["sensor_id"]}))
    assert alerts
    assert any(alert["lectura_id"] == str(lectura_id) for alert in alerts)
    assert any(alert.get("incidente_id") is not None for alert in alerts)

    with get_postgres_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT tipo, estado, descripcion FROM incidente WHERE id_envio=%s",
                (data["shipment_id"],),
            )
            incidents = cursor.fetchall()
    assert incidents
    assert any("temperatura" in str(row[0]).lower() or "Temperatura" in str(row[0]) for row in incidents)
    assert any(f"[iot:{data['sensor_id']}:{lectura_id}:" in (row[2] or "") for row in incidents)


def test_mensajeria_privada_y_grupal_mongo_postgres(synthetic_logistics):
    from app.repositories.mensajeria_repository import (
        registrar_mensaje_privado,
        obtener_bandeja_entrada,
        crear_grupo,
        agregar_miembro_grupo,
        registrar_mensaje_grupo,
        obtener_mensajes_grupo,
    )

    data = synthetic_logistics
    sender, recipient = data["user_ids"]

    private_id = registrar_mensaje_privado(sender, recipient, f"Privado IT {data['token']}")
    inbox = obtener_bandeja_entrada(recipient)
    assert any(str(message["_id"]) == private_id for message in inbox)

    group_id = crear_grupo(f"Grupo IT {data['token']}", "Grupo sintético", sender)
    assert agregar_miembro_grupo(group_id, recipient) is True
    group_message_id = registrar_mensaje_grupo(sender, group_id, f"Grupo IT {data['token']}")
    messages = obtener_mensajes_grupo(group_id, recipient)
    assert any(str(message["_id"]) == group_message_id for message in messages)


def test_prediccion_calculo_persistencia_e_historial(synthetic_logistics):
    from app.services.predicciones_service import calcular_riesgo
    from app.repositories.predicciones_repository import (
        obtener_datos_riesgo,
        guardar_prediccion,
        obtener_historial_predicciones,
    )

    data = synthetic_logistics
    now = datetime.now(timezone.utc)
    context = obtener_datos_riesgo(data["shipment_id"])
    prediction = calcular_riesgo(context, ahora=now)
    prediction_id = guardar_prediccion(prediction)

    history = obtener_historial_predicciones(data["shipment_id"])
    assert len(history) == 1
    assert str(history[0]["_id"]) == prediction_id
    assert history[0]["envio_id"] == data["shipment_id"]
    assert history[0]["metodo"] == "reglas_heuristicas_v3"
    assert history[0]["nivel_riesgo"] == prediction["nivel_riesgo"]
