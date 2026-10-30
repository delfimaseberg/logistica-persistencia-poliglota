"""Cierre mensual operativo y apertura de cuenta corriente."""

from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from app.repositories import cierre_cuenta_repository as repo
from app.services import cierre_cuenta_service as service


APROBADA = datetime(2026, 10, 30, tzinfo=timezone.utc)


def mov(id_mov, tipo, importe, fecha, ref):
    return {"id_movimiento": id_mov, "moneda": "ARS", "tipo_movimiento": tipo,
            "importe_firmado": Decimal(importe), "fecha_contable": fecha,
            "periodo_origen": None, "tipo_origen": tipo,
            "referencia_origen": ref, "referencia_documental": None}


def datos_cliente_4():
    """Caso real del cliente 4: factura 3 (27/10) sin movimiento, cubierta
    por la apertura del 28/10; factura 4 y pago 5 (30/10) con movimiento."""
    return {
        "cuenta": {"saldo": Decimal("31500.00"), "moneda": "ARS"},
        "apertura": {
            "id_apertura": 1, "id_cliente": 4, "moneda": "ARS",
            "saldo_inicial": Decimal("2000.00"),
            "fecha_vigencia": date(2026, 10, 28),
            "referencia_fuente": "Saldo al 27/10/2026", "aprobado_por": 4,
            "aprobado_en": APROBADA,
        },
        "facturas": [
            {"id_factura": 3, "fecha_emision": date(2026, 10, 27),
             "total": Decimal("2000.00"), "estado": "Parcial", "moneda": "ARS"},
            {"id_factura": 4, "fecha_emision": date(2026, 10, 30),
             "total": Decimal("30000.00"), "estado": "Pendiente", "moneda": "ARS"},
        ],
        "pagos": [{"id_pago": 5, "id_factura": 3,
                   "fecha": datetime(2026, 10, 30, 14, tzinfo=timezone.utc),
                   "monto": Decimal("500.00"), "moneda": "ARS",
                   "estado_factura": "Parcial"}],
        "correcciones": [],
        "movimientos": [
            mov(1, "FACTURA", "30000.00", date(2026, 10, 30), "4"),
            mov(2, "PAGO", "-500.00", date(2026, 10, 30), "5"),
        ],
        "periodos_cerrados": [],
    }


# ------------------------------------------------------ período parcial

def test_primer_periodo_parcial_desde_la_apertura():
    r = service.calcular_snapshot_cierre(datos_cliente_4(), date(2026, 10, 1))
    assert r["saldo_inicial"] == Decimal("2000.00")
    assert r["total_facturas"] == Decimal("30000.00")
    assert r["total_pagos"] == Decimal("500.00")
    assert r["saldo_final"] == Decimal("31500.00")


def test_no_se_cierra_un_mes_anterior_a_la_apertura():
    with pytest.raises(service.CierreBloqueado, match="anterior a la apertura"):
        service.calcular_snapshot_cierre(datos_cliente_4(), date(2026, 9, 1))


def test_documento_posterior_a_la_apertura_sin_movimiento_bloquea():
    datos = datos_cliente_4()
    datos["apertura"]["fecha_vigencia"] = date(2026, 10, 27)
    with pytest.raises(service.CierreBloqueado, match="Factura 3"):
        service.calcular_snapshot_cierre(datos, date(2026, 10, 1))


# ------------------------------------------------------ mes terminado

def test_no_se_cierra_un_mes_que_no_termino(monkeypatch):
    ejecutar = MagicMock()
    monkeypatch.setattr(repo, "ejecutar_cierre_atomico", ejecutar)
    r = service.cerrar_cuenta_mensual(4, date(2026, 10, 1), hoy=date(2026, 10, 30))
    assert r == {"estado": "BLOQUEADO",
                 "motivo": "El período 2026-10 todavía no terminó."}
    ejecutar.assert_not_called()


def test_el_mes_se_cierra_desde_el_primer_dia_del_siguiente(monkeypatch):
    monkeypatch.setattr(repo, "ejecutar_cierre_atomico",
                        lambda cliente, periodo, calcular: {"id_cierre": 1,
                            **calcular(datos_cliente_4())})
    r = service.cerrar_cuenta_mensual(4, date(2026, 10, 1), hoy=date(2026, 11, 1))
    assert r["estado"] == "CERRADO" and r["saldo_final"] == Decimal("31500.00")


def test_siguiente_mes_cruza_el_anio():
    assert service.siguiente_mes(date(2026, 12, 1)) == date(2027, 1, 1)


# --------------------------------------------- cierre de todos los clientes

def test_cierre_de_todos_resume_cerrados_bloqueados_y_ya_cerrados(monkeypatch):
    monkeypatch.setattr(repo, "listar_clientes_con_cuenta",
                        lambda: [(3, "Distribuidora"), (4, "Alimentos"),
                                 (5, "Sin apertura"), (6, "Repetido")])

    def cerrar(id_cliente, periodo, hoy=None):
        if id_cliente == 5:
            return {"estado": "BLOQUEADO", "motivo": "No hay una apertura"}
        if id_cliente == 6:
            raise service.CierreDuplicado("Ya existe el cierre 9")
        return {"estado": "CERRADO", "id_cierre": id_cliente, "saldo_final": Decimal("0")}

    monkeypatch.setattr(service, "cerrar_cuenta_mensual", cerrar)
    r = service.cerrar_mes_todos(date(2026, 10, 15))

    assert r["periodo"] == date(2026, 10, 1)
    assert [c["id_cliente"] for c in r["cerrados"]] == [3, 4]
    assert r["bloqueados"] == [{"id_cliente": 5, "cliente": "Sin apertura",
                                "motivo": "No hay una apertura"}]
    assert [y["id_cliente"] for y in r["ya_cerrados"]] == [6]
    assert r["errores"] == []


def test_error_de_un_cliente_no_frena_al_resto(monkeypatch):
    monkeypatch.setattr(repo, "listar_clientes_con_cuenta",
                        lambda: [(3, "A"), (4, "B")])
    resultados = iter([RuntimeError("fallo SQL"),
                       {"estado": "CERRADO", "id_cierre": 2}])

    def cerrar(*_a, **_k):
        valor = next(resultados)
        if isinstance(valor, Exception):
            raise valor
        return valor

    monkeypatch.setattr(service, "cerrar_cuenta_mensual", cerrar)
    r = service.cerrar_mes_todos(date(2026, 10, 1))
    assert r["errores"] == [{"id_cliente": 3, "cliente": "A", "error": "fallo SQL"}]
    assert [c["id_cliente"] for c in r["cerrados"]] == [4]


# ------------------------------------------------------------- apertura

@pytest.mark.parametrize("saldo, fecha, referencia, texto", [
    ("abc", date(2026, 10, 28), "ref", "no es un importe"),
    ("10", date(2026, 11, 30), "ref", "futura"),
    ("10", datetime(2026, 10, 28), "ref", "fecha calendario"),
    ("10", date(2026, 10, 28), "  ", "referencia"),
])
def test_validaciones_de_apertura(saldo, fecha, referencia, texto):
    with pytest.raises(service.CierreBloqueado, match=texto):
        service.validar_datos_apertura(saldo, fecha, referencia, hoy=date(2026, 10, 30))


def test_previsualizar_apertura_concilia_con_los_datos_reales(monkeypatch):
    datos = datos_cliente_4()
    datos["apertura"] = None
    monkeypatch.setattr(repo, "leer_datos_cierre", lambda _id: datos)
    monkeypatch.setattr(repo, "calcular_saldo_documentos",
                        lambda _id, _f: (Decimal("2000"), Decimal("0"), Decimal("2000")))
    vista = service.previsualizar_apertura(4, Decimal("2000.00"), date(2026, 10, 28),
                                           hoy=date(2026, 10, 30))
    assert vista["concilia"] is True
    assert vista["snapshot"]["saldo_final"] == Decimal("31500.00")
    assert vista["saldo_documentos"]["saldo"] == Decimal("2000")


def test_previsualizar_apertura_con_saldo_equivocado_avisa(monkeypatch):
    datos = datos_cliente_4()
    datos["apertura"] = None
    monkeypatch.setattr(repo, "leer_datos_cierre", lambda _id: datos)
    monkeypatch.setattr(repo, "calcular_saldo_documentos",
                        lambda _id, _f: (0, 0, 0))
    vista = service.previsualizar_apertura(4, Decimal("1999.00"), date(2026, 10, 28),
                                           hoy=date(2026, 10, 30))
    assert vista["concilia"] is False and "no concilia" in vista["motivo"]


def crear_conexion_mock(cursor):
    conexion = MagicMock()
    conexion.__enter__.return_value = conexion
    conexion.cursor.return_value.__enter__.return_value = cursor
    return conexion


def registrar(cursor):
    with patch.object(repo, "get_postgres_connection",
                      return_value=crear_conexion_mock(cursor)):
        return repo.registrar_apertura(4, Decimal("2000"), date(2026, 10, 28),
                                       "ref", 4)


def test_apertura_aprobada_por_usuario_interno():
    cursor = MagicMock()
    cursor.fetchone.side_effect = [("ARS",), ("ACTIVO", None, None, None, 5),
                                   None, (11,)]
    assert registrar(cursor) == 11
    insert = cursor.execute.call_args_list[-1].args
    assert "INSERT INTO apertura_cuenta_corriente" in insert[0]
    assert insert[1] == (4, "ARS", Decimal("2000"), date(2026, 10, 28), "ref", 4)


@pytest.mark.parametrize("aprobador", [
    ("ACTIVO", 4, None, None, 5),   # usuario de cliente (aunque sea nivel 5)
    ("ACTIVO", None, 2, None, 3),   # usuario de proveedor
    ("ACTIVO", None, None, 1, 3),   # usuario de operador
])
def test_apertura_no_la_aprueba_un_usuario_externo(aprobador):
    cursor = MagicMock()
    cursor.fetchone.side_effect = [("ARS",), aprobador]
    with pytest.raises(ValueError, match="usuario interno"):
        registrar(cursor)


def test_apertura_no_se_cambia_si_ya_hay_cierres():
    cursor = MagicMock()
    cursor.fetchone.side_effect = [("ARS",), ("ACTIVO", None, None, None, 5), (1,)]
    with pytest.raises(ValueError, match="ya tiene cierres"):
        registrar(cursor)


def test_saldo_sugerido_usa_documentos_anteriores_a_la_vigencia():
    cursor = MagicMock()
    cursor.fetchone.return_value = (Decimal("65000"), Decimal("63000"))
    with patch.object(repo, "get_postgres_connection",
                      return_value=crear_conexion_mock(cursor)):
        r = repo.calcular_saldo_documentos(4, date(2026, 10, 28))
    assert r == (Decimal("65000"), Decimal("63000"), Decimal("2000"))
    sql = cursor.execute.call_args.args[0]
    assert "fecha_emision < %s" in sql and "::date < %s" in sql
