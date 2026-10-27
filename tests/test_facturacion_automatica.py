from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from app.services import facturacion_automatica_service as service
from app.repositories import facturacion_repository as repository


FECHA_EMISION = date(2026, 3, 5)
FECHA_ENTREGA = datetime(2026, 3, 4, 23, 30, tzinfo=timezone.utc)


def envio(estado="Entregado", id_envio=45):
    return (
        id_envio,
        12,
        "Cliente de prueba",
        "Origen de prueba",
        "Destino de prueba",
        estado,
        "Normal",
        datetime(2026, 3, 1, tzinfo=timezone.utc),
    )


def evento_entrega(id_envio=45):
    return {
        "_id": "evento-entrega-test",
        "envio_id": id_envio,
        "tipo": "ENTREGADO",
        "fecha_hora": FECHA_ENTREGA,
    }


def contexto_tarifa(configuracion=None):
    tarifa = {
        "id_tarifa": 81,
        "id_envio": 45,
        "version": 1,
        "estado": "APROBADA",
        "moneda": "TST",
        "importe_base": "1.00",
        "importe_impuestos": "0.00",
        "importe_total": "1.00",
        "id_configuracion_fiscal": 9,
        "tratamiento_impositivo": "perfil de prueba",
        "tasa_impositiva": None,
        "referencia_aprobacion": "tarifa-test-aprobada",
        "aprobado_por": 7,
        "aprobado_en": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }
    fiscal = configuracion or {
        "id_configuracion_fiscal": 9,
        "codigo": "PERFIL_TEST",
        "version": 1,
        "tratamiento": "perfil de prueba",
        "tasa": None,
        "vigente_desde": date(2026, 1, 1),
        "vigente_hasta": None,
        "referencia_aprobacion": "fiscal-test-aprobado",
        "aprobado_por": 7,
        "aprobado_en": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "aprobada": True,
        "activa": True,
    }
    return {
        "tarifa": tarifa,
        "configuracion_fiscal": fiscal,
        "moneda_cuenta": "TST",
    }


def preparar_mocks(monkeypatch, estado_pg="Entregado", eventos=None, ctx=None):
    monkeypatch.setattr(service, "FACTURACION_AUTOMATICA_HABILITADA", True)
    monkeypatch.setattr(service, "listar_envios", lambda: [envio(estado_pg)])
    monkeypatch.setattr(
        service,
        "listar_eventos_entregados",
        lambda: [evento_entrega()] if eventos is None else eventos,
    )
    monkeypatch.setattr(service, "listar_pendientes_estado", lambda: [])
    monkeypatch.setattr(
        service,
        "obtener_contexto_tarifas_aprobadas",
        lambda _id: [contexto_tarifa()] if ctx is None else ctx,
    )
    monkeypatch.setattr(service, "existe_factura_original", lambda *_: False)
    monkeypatch.setattr(service, "contar_facturas_sin_envio_cliente", lambda _id: 0)
    monkeypatch.setattr(service, "emitir_factura_automatica", lambda **_kwargs: 901)
    audit = MagicMock()
    monkeypatch.setattr(service, "registrar_auditoria_facturacion", audit)
    return audit


def test_entrega_tarifa_y_configuracion_validas_emiten_una_factura():
    audit = MagicMock()
    from unittest.mock import patch

    with patch.object(service, "FACTURACION_AUTOMATICA_HABILITADA", True), \
         patch.object(service, "listar_envios", return_value=[envio()]), \
         patch.object(service, "listar_eventos_entregados", return_value=[evento_entrega()]), \
         patch.object(service, "listar_pendientes_estado", return_value=[]), \
         patch.object(service, "obtener_contexto_tarifas_aprobadas", return_value=[contexto_tarifa()]), \
         patch.object(service, "existe_factura_original", return_value=False), \
         patch.object(service, "contar_facturas_sin_envio_cliente", return_value=0), \
         patch.object(service, "registrar_auditoria_facturacion", audit), \
         patch.object(service, "emitir_factura_automatica", return_value=901) as emitir:
        resultado = service.procesar_facturacion_automatica(FECHA_EMISION)

    assert resultado["facturas_emitidas"] == 1
    assert resultado["bloqueadas"] == []
    assert resultado["facturas"][0]["id_factura"] == 901
    emitir.assert_called_once_with(
        id_envio=45,
        evento_entrega_id="evento-entrega-test",
        fecha_entrega=FECHA_ENTREGA,
        fecha_emision=FECHA_EMISION,
        id_tarifa=81,
    )
    audit.assert_not_called()  # El éxito se audita en la transacción de emisión.


@pytest.mark.parametrize(
    "estado,eventos,pendientes,motivo",
    [
        ("En tránsito", [evento_entrega()], [], "no coincide"),
        ("Entregado", [], [], "No existe evidencia"),
        (
            "Entregado",
            [evento_entrega()],
            [{"evento_id": "evento-entrega-test", "resuelto": False}],
            "sigue pendiente",
        ),
        (
            "Entregado",
            [evento_entrega(), evento_entrega()],
            [],
            "exactamente un evento",
        ),
    ],
)
def test_inconsistencias_de_entrega_bloquean_y_auditan(
    monkeypatch, estado, eventos, pendientes, motivo
):
    audit = preparar_mocks(monkeypatch, estado_pg=estado, eventos=eventos)
    monkeypatch.setattr(service, "listar_pendientes_estado", lambda: pendientes)
    emitir = MagicMock()
    monkeypatch.setattr(service, "emitir_factura_automatica", emitir)

    resultado = service.procesar_facturacion_automatica(FECHA_EMISION)

    assert resultado["facturas_emitidas"] == 0
    assert motivo.lower() in resultado["bloqueadas"][0]["motivo"].lower()
    emitir.assert_not_called()
    assert audit.call_args.kwargs["resultado"] == "BLOQUEADA"


def test_tarifa_ausente_bloquea_y_registra_motivo(monkeypatch):
    audit = preparar_mocks(monkeypatch, ctx=[])
    emitir = MagicMock()
    monkeypatch.setattr(service, "emitir_factura_automatica", emitir)

    resultado = service.procesar_facturacion_automatica(FECHA_EMISION)

    assert "No hay una tarifa aprobada" in resultado["bloqueadas"][0]["motivo"]
    assert audit.call_args.kwargs["resultado"] == "BLOQUEADA"
    emitir.assert_not_called()


def test_configuracion_fiscal_incompleta_bloquea_emision(monkeypatch):
    contexto = contexto_tarifa({"aprobada": True, "activa": False})
    audit = preparar_mocks(monkeypatch, ctx=[contexto])
    emitir = MagicMock()
    monkeypatch.setattr(service, "emitir_factura_automatica", emitir)

    resultado = service.procesar_facturacion_automatica(FECHA_EMISION)

    assert "no está activa" in resultado["bloqueadas"][0]["motivo"]
    assert audit.call_args.kwargs["resultado"] == "BLOQUEADA"
    emitir.assert_not_called()


def test_factura_preexistente_impide_la_reejecucion():
    from unittest.mock import patch

    audit = MagicMock()
    with patch.object(service, "FACTURACION_AUTOMATICA_HABILITADA", True), \
         patch.object(service, "listar_envios", return_value=[envio()]), \
         patch.object(service, "listar_eventos_entregados", return_value=[evento_entrega()]), \
         patch.object(service, "listar_pendientes_estado", return_value=[]), \
         patch.object(service, "obtener_contexto_tarifas_aprobadas", return_value=[contexto_tarifa()]), \
         patch.object(service, "existe_factura_original", side_effect=[False, True]), \
         patch.object(service, "contar_facturas_sin_envio_cliente", return_value=0), \
         patch.object(service, "registrar_auditoria_facturacion", audit), \
         patch.object(service, "emitir_factura_automatica", return_value=901) as emitir:
        primera = service.procesar_facturacion_automatica(FECHA_EMISION)
        segunda = service.procesar_facturacion_automatica(FECHA_EMISION)

    assert primera["facturas_emitidas"] == 1
    assert segunda["facturas_emitidas"] == 0
    assert "Ya existe" in segunda["bloqueadas"][0]["motivo"]
    emitir.assert_called_once()


def test_facturas_manuales_sin_envio_bloquean_por_ambiguedad(monkeypatch):
    audit = preparar_mocks(monkeypatch)
    monkeypatch.setattr(service, "contar_facturas_sin_envio_cliente", lambda _id: 1)
    emitir = MagicMock()
    monkeypatch.setattr(service, "emitir_factura_automatica", emitir)

    resultado = service.procesar_facturacion_automatica(FECHA_EMISION)

    assert "sin vínculo a envío" in resultado["bloqueadas"][0]["motivo"]
    assert audit.call_args.kwargs["resultado"] == "BLOQUEADA"
    emitir.assert_not_called()


def test_error_durante_emision_se_registra_y_no_se_informa_como_exito(monkeypatch):
    audit = preparar_mocks(monkeypatch)
    monkeypatch.setattr(
        service,
        "emitir_factura_automatica",
        MagicMock(side_effect=RuntimeError("fallo de escritura")),
    )

    resultado = service.procesar_facturacion_automatica(FECHA_EMISION)

    assert resultado["facturas_emitidas"] == 0
    assert "fallo de escritura" in resultado["errores"][0]["motivo"]
    assert audit.call_args.kwargs["resultado"] == "ERROR"


def test_gate_desactivado_no_consulta_ni_escribe_bases():
    with patch.object(service, "FACTURACION_AUTOMATICA_HABILITADA", False), \
         patch.object(service, "listar_envios") as listar:
        resultado = service.procesar_facturacion_automatica(FECHA_EMISION)

    listar.assert_not_called()
    assert resultado["facturas_emitidas"] == 0
    assert "deshabilitada" in resultado["bloqueadas"][0]["motivo"]


def test_repositorio_guarda_snapshot_saldo_ledger_y_auditoria_en_transaccion():
    cursor = MagicMock()
    cursor.rowcount = 1
    cursor.fetchone.side_effect = [
        (12, "Entregado", "ACTIVO"),
        ("TST",),
        None,
        (0,),
        (
            81, 45, 1,
            Decimal("1.00"), Decimal("0.00"), Decimal("1.00"),
            "TST", 9, "perfil de prueba", None,
            "APROBADA", "tarifa-test-aprobada", 7,
            datetime(2026, 1, 1, tzinfo=timezone.utc),
            "PERFIL_TEST", 1, "perfil de prueba", None,
            date(2026, 1, 1), None, "fiscal-test-aprobado", 7,
            datetime(2026, 1, 1, tzinfo=timezone.utc), True,
        ),
        (901,),
    ]
    cursor_context = MagicMock()
    cursor_context.__enter__.return_value = cursor
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.cursor.return_value = cursor_context

    with patch.object(
        repository, "get_postgres_connection", return_value=connection
    ):
        id_factura = repository.emitir_factura_automatica(
            id_envio=45,
            evento_entrega_id="evento-entrega-test",
            fecha_entrega=FECHA_ENTREGA,
            fecha_emision=FECHA_EMISION,
            id_tarifa=81,
        )

    assert id_factura == 901
    assert connection.__exit__.call_args.args == (None, None, None)
    sentencias = [str(llamada.args[0]) for llamada in cursor.execute.call_args_list]
    assert any("INSERT INTO factura" in sql for sql in sentencias)
    assert any("UPDATE cuenta_corriente" in sql for sql in sentencias)
    assert any("INSERT INTO movimiento_cuenta_corriente" in sql for sql in sentencias)
    assert any("INSERT INTO auditoria_facturacion_periodica" in sql for sql in sentencias)
