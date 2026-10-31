from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from app.utils.validaciones_financieras import (
    FinanzasNoConfiguradas,
    validar_apertura_verificada,
    validar_conciliacion_saldo,
    validar_correccion_factura,
    validar_evento_entrega,
    validar_factura_original_no_duplicada,
    validar_periodo_movimiento_tardio,
    validar_tarifa_aprobada,
)


def tarifa_valida():
    return {
        "estado": "APROBADA",
        "moneda": "TST",
        "importe_base": "1.00",
        "importe_impuestos": "0.00",
        "importe_total": "1.00",
        "tratamiento_impositivo": "perfil configurado",
        "tasa_impositiva": None,
        "referencia_aprobacion": "aprobacion-documentada",
        "aprobado_por": 7,
        "aprobado_en": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "id_configuracion_fiscal": 3,
    }


def configuracion_fiscal_valida():
    return {
        "id_configuracion_fiscal": 3,
        "codigo": "PERFIL_TEST",
        "version": 1,
        "tratamiento": "perfil configurado",
        "tasa": None,
        "vigente_desde": date(2020, 1, 1),
        "vigente_hasta": None,
        "referencia_aprobacion": "fiscal-aprobado-test",
        "aprobado_por": 7,
        "aprobado_en": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "aprobada": True,
        "activa": True,
    }


def evento_entrega_valido():
    return {
        "_id": "mongo-event-1",
        "envio_id": 45,
        "tipo": "ENTREGADO",
        "fecha_hora": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }


def apertura_valida(saldo="0.00"):
    return {
        "saldo_inicial": saldo,
        "moneda": "TST",
        "referencia_fuente": "acta-de-apertura-001",
        "fecha_vigencia": datetime(2026, 1, 1).date(),
        "aprobado_por": 12,
        "aprobado_en": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }


def test_tarifa_aprobada_devuelve_importes_explicitos_sin_recalcularlos():
    resultado = validar_tarifa_aprobada(
        tarifa_valida(),
        "TST",
        configuracion_fiscal_valida(),
        date(2026, 1, 1),
    )

    assert resultado["importe_base"] == Decimal("1.00")
    assert resultado["importe_impuestos"] == Decimal("0.00")
    assert resultado["importe_total"] == Decimal("1.00")
    assert resultado["moneda"] == "TST"


def test_configuracion_fiscal_fuera_de_vigencia_bloquea_emision():
    configuracion = {
        **configuracion_fiscal_valida(),
        "vigente_hasta": date(2025, 12, 31),
    }

    with pytest.raises(FinanzasNoConfiguradas, match="no está vigente"):
        validar_tarifa_aprobada(
            tarifa_valida(), "TST", configuracion, date(2026, 1, 1)
        )


@pytest.mark.parametrize(
    "tarifa,moneda,configuracion,fragmento",
    [
        (None, "TST", configuracion_fiscal_valida(), "no tiene una tarifa"),
        (tarifa_valida(), None, configuracion_fiscal_valida(), "moneda.*no está configurada"),
        (tarifa_valida(), "XXX", configuracion_fiscal_valida(), "no coincide"),
        (tarifa_valida(), "TST", None, "configuración fiscal aprobada"),
        ({**tarifa_valida(), "estado": "BORRADOR"}, "TST", configuracion_fiscal_valida(), "no está aprobada"),
        ({**tarifa_valida(), "importe_total": None}, "TST", configuracion_fiscal_valida(), "importe total"),
        ({**tarifa_valida(), "tratamiento_impositivo": ""}, "TST", configuracion_fiscal_valida(), "tratamiento impositivo"),
    ],
)
def test_tarifa_incompleta_o_no_configurada_bloquea_emision(
    tarifa, moneda, configuracion, fragmento
):
    with pytest.raises(FinanzasNoConfiguradas, match=fragmento):
        validar_tarifa_aprobada(
            tarifa, moneda, configuracion, date(2026, 1, 1)
        )


def test_evento_entregado_valido_requiere_estado_concordante():
    resultado = validar_evento_entrega(
        45,
        evento_entrega_valido(),
        "Entregado",
        cantidad_eventos_entrega=1,
    )

    assert resultado["evento_id"] == "mongo-event-1"
    assert resultado["fecha_hora"] == evento_entrega_valido()["fecha_hora"]


@pytest.mark.parametrize(
    "evento,estado,pendiente,cantidad,fragmento",
    [
        (None, "Entregado", False, 1, "No hay un evento de entrega válido"),
        (evento_entrega_valido(), "En tránsito", False, 1, "no coincide"),
        (evento_entrega_valido(), "Entregado", True, 1, "actualización de estado pendiente"),
        (evento_entrega_valido(), "Entregado", False, 2, "exactamente un evento"),
        ({**evento_entrega_valido(), "envio_id": 46}, "Entregado", False, 1, "no corresponde"),
        ({**evento_entrega_valido(), "fecha_hora": datetime(2026, 1, 1)}, "Entregado", False, 1, "zona horaria"),
    ],
)
def test_evento_o_estado_inconsistente_bloquea_facturacion(
    evento, estado, pendiente, cantidad, fragmento
):
    with pytest.raises(FinanzasNoConfiguradas, match=fragmento):
        validar_evento_entrega(45, evento, estado, pendiente, cantidad)


def test_factura_original_existente_bloquea_duplicado():
    with pytest.raises(FinanzasNoConfiguradas, match="Ya existe"):
        validar_factura_original_no_duplicada(existe_factura_envio=True)


def test_correccion_debe_tener_vinculo_y_aprobacion_auditable():
    correccion = {
        "id_factura_original": 51,
        "tipo": "CREDITO",
        "importe": "1.00",
        "importe_base": "1.00",
        "importe_impuestos": "0.00",
        "moneda": "TST",
        "id_configuracion_fiscal": 3,
        "tratamiento_impositivo": "perfil configurado",
        "motivo": "motivo de prueba",
        "referencia_aprobacion": "aprobacion-correccion-test",
        "idempotency_key": "correccion-test-1",
        "aprobado_por": 12,
        "aprobada_en": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }

    assert validar_correccion_factura(51, correccion, "TST") == Decimal("1.00")
    with pytest.raises(FinanzasNoConfiguradas, match="no referencia"):
        validar_correccion_factura(52, correccion, "TST")


def test_movimiento_tardio_va_a_periodo_abierto_y_no_al_origen():
    origen = date(2026, 1, 1)
    abierto = date(2026, 3, 1)

    validar_periodo_movimiento_tardio(abierto, abierto, origen)
    with pytest.raises(FinanzasNoConfiguradas, match="período abierto"):
        validar_periodo_movimiento_tardio(origen, abierto, origen)


def test_saldo_inicial_sin_documentacion_bloquea_cierre():
    with pytest.raises(FinanzasNoConfiguradas, match="apertura.*verificada"):
        validar_apertura_verificada(None, "ARS")


def test_cero_solo_se_acepta_como_apertura_con_evidencia_y_aprobacion():
    resultado = validar_apertura_verificada(apertura_valida(), "TST")

    assert resultado["saldo_inicial"] == Decimal("0.00")
    assert resultado["referencia_fuente"] == "acta-de-apertura-001"


def test_diferencia_de_conciliacion_no_se_ajusta_sin_aprobacion():
    with pytest.raises(FinanzasNoConfiguradas, match="aprobación documentada"):
        validar_conciliacion_saldo("125", "100")


def test_diferencia_con_aprobacion_documentada_se_devuelve_sin_modificar_saldo():
    diferencia = validar_conciliacion_saldo(
        "125",
        "100",
        {
            "referencia": "ajuste-001",
            "aprobado_por": 12,
            "aprobado_en": datetime(2026, 1, 1, tzinfo=timezone.utc),
        },
    )

    assert diferencia == Decimal("25")


def test_migraciones_financieras_preparan_unicidad_y_snapshots_sin_datos():
    raiz = Path(__file__).resolve().parents[1]
    sql_cierres = (
        raiz / "scripts" / "migrations"
        / "003_cierres_y_movimientos_financieros.sql"
    ).read_text(encoding="utf-8")
    sql_facturas = (
        raiz / "scripts" / "migrations"
        / "004_tarifas_facturacion_auditable.sql"
    ).read_text(encoding="utf-8")
    sql_auditoria = (
        raiz / "scripts" / "migrations"
        / "005_facturacion_periodica_auditoria.sql"
    ).read_text(encoding="utf-8")

    assert "UNIQUE (id_cliente, periodo)" in sql_cierres
    assert "referencia_fuente TEXT NOT NULL" in sql_cierres
    assert "CREATE TABLE IF NOT EXISTS movimiento_cuenta_corriente" in sql_cierres
    assert "CREATE TABLE IF NOT EXISTS tarifa_envio" in sql_facturas
    assert "uq_factura_original_envio" in sql_facturas
    assert "uq_factura_evento_entrega" in sql_facturas
    assert "CREATE TABLE IF NOT EXISTS correccion_factura" in sql_facturas
    assert "id_envio BIGINT," in sql_facturas
    assert "WHERE id_envio IS NOT NULL" in sql_facturas
    assert "fecha_entrega TIMESTAMPTZ" in sql_auditoria
    assert "'BLOQUEADA', 'ERROR', 'FACTURADA'" in sql_auditoria
