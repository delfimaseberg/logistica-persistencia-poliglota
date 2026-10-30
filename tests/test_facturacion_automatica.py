"""Facturación automática por envío (facturacion_automatica_service)."""

from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from app.repositories.facturacion_repository import FacturaExistente
from app.services import facturacion_automatica_service as service
from app.services.cotizacion_envio import CotizacionImposible


CORTE = date(2026, 10, 31)
ENTREGA = datetime(2026, 10, 20, tzinfo=timezone.utc)


def candidato(id_envio, cliente="Cliente A"):
    return (id_envio, 7, cliente, "Origen", "Destino", ENTREGA, 2)


def preparar(monkeypatch, candidatos, emitir):
    listar = MagicMock(return_value=candidatos)
    auditoria = MagicMock()
    monkeypatch.setattr(service, "listar_envios_facturables", listar)
    monkeypatch.setattr(service, "emitir_factura_envio", emitir)
    monkeypatch.setattr(service, "registrar_auditoria_facturacion", auditoria)
    return listar, auditoria


def factura(id_factura, total="1210.00"):
    return {"id_factura": id_factura, "total": Decimal(total)}


def test_factura_cada_envio_entregado_sin_factura_hasta_el_corte(monkeypatch):
    emitir = MagicMock(side_effect=[factura(901), factura(902, "2420.00")])
    listar, auditoria = preparar(monkeypatch, [candidato(45), candidato(46)], emitir)

    resumen = service.procesar_facturacion_automatica(CORTE)

    listar.assert_called_once_with(fecha_corte=CORTE)
    assert [c.args[0] for c in emitir.call_args_list] == [45, 46]
    assert all(c.kwargs == {"origen": "ENVIO_AUTOMATICA"} for c in emitir.call_args_list)
    assert resumen["candidatos"] == 2
    assert [(f["id_envio"], f["id_factura"]) for f in resumen["facturados"]] == [
        (45, 901), (46, 902)]
    assert resumen["omitidos"] == [] and resumen["errores"] == []
    assert [c.kwargs["resultado"] for c in auditoria.call_args_list] == [
        "FACTURADA", "FACTURADA"]


def test_reejecucion_no_duplica(monkeypatch):
    # Tras la primera corrida los envíos ya tienen factura y dejan de ser
    # candidatos; si otro proceso gana la carrera, el envío se informa omitido.
    emitir = MagicMock(side_effect=FacturaExistente("El envío ya fue facturado."))
    preparar(monkeypatch, [candidato(45)], emitir)
    resumen = service.procesar_facturacion_automatica(CORTE)
    assert resumen["facturados"] == []
    assert resumen["omitidos"][0]["motivo"] == "El envío ya fue facturado."

    preparar(monkeypatch, [], MagicMock())
    resumen = service.procesar_facturacion_automatica(CORTE)
    assert resumen["candidatos"] == 0 and resumen["facturados"] == []


def test_omitidos_con_motivo_y_el_resto_se_factura(monkeypatch):
    emitir = MagicMock(side_effect=[
        CotizacionImposible("El envío no tiene tramos registrados."),
        ValueError("El cliente no está activo."),
        factura(903),
    ])
    _, auditoria = preparar(
        monkeypatch, [candidato(45), candidato(46), candidato(47)], emitir)

    resumen = service.procesar_facturacion_automatica(CORTE)

    assert [(o["id_envio"], o["motivo"]) for o in resumen["omitidos"]] == [
        (45, "El envío no tiene tramos registrados."),
        (46, "El cliente no está activo."),
    ]
    assert [f["id_envio"] for f in resumen["facturados"]] == [47]
    assert [c.kwargs["resultado"] for c in auditoria.call_args_list] == [
        "BLOQUEADA", "BLOQUEADA", "FACTURADA"]


def test_error_inesperado_se_informa_y_no_frena_al_resto(monkeypatch):
    emitir = MagicMock(side_effect=[RuntimeError("conexión perdida"), factura(904)])
    _, auditoria = preparar(monkeypatch, [candidato(45), candidato(46)], emitir)

    resumen = service.procesar_facturacion_automatica(CORTE)

    assert resumen["errores"] == [
        {"id_envio": 45, "cliente": "Cliente A", "error": "conexión perdida"}]
    assert [f["id_envio"] for f in resumen["facturados"]] == [46]
    assert auditoria.call_args_list[0].kwargs["resultado"] == "ERROR"


def test_sin_corte_usa_hoy_argentino(monkeypatch):
    listar, _ = preparar(monkeypatch, [], MagicMock())
    monkeypatch.setattr(service, "hoy_argentina", lambda: date(2026, 11, 2))
    resumen = service.procesar_facturacion_automatica()
    listar.assert_called_once_with(fecha_corte=date(2026, 11, 2))
    assert resumen["fecha_corte"] == date(2026, 11, 2)


def test_error_al_listar_candidatos_se_propaga(monkeypatch):
    emitir = MagicMock()
    preparar(monkeypatch, [], emitir)
    monkeypatch.setattr(service, "listar_envios_facturables",
                        MagicMock(side_effect=RuntimeError("PostgreSQL no disponible")))
    with pytest.raises(RuntimeError, match="PostgreSQL no disponible"):
        service.procesar_facturacion_automatica(CORTE)
    emitir.assert_not_called()


def test_corte_debe_ser_fecha_calendario():
    with pytest.raises(ValueError, match="fecha calendario"):
        service.procesar_facturacion_automatica(datetime(2026, 10, 31))


def test_falla_de_auditoria_no_cambia_el_resultado(monkeypatch):
    preparar(monkeypatch, [candidato(45)], MagicMock(return_value=factura(905)))
    monkeypatch.setattr(service, "registrar_auditoria_facturacion",
                        MagicMock(side_effect=RuntimeError("auditoría caída")))
    resumen = service.procesar_facturacion_automatica(CORTE)
    assert [f["id_factura"] for f in resumen["facturados"]] == [905]


def test_ya_no_existen_el_bloqueo_por_facturas_sin_envio_ni_el_interruptor():
    assert not hasattr(service, "FACTURACION_AUTOMATICA_HABILITADA")
    from app.repositories import facturacion_repository as repo
    assert not hasattr(repo, "contar_facturas_sin_envio_cliente")
    assert not hasattr(repo, "emitir_factura")
