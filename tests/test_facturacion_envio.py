"""Factura por envío (facturacion_repository.emitir_factura_envio y afines)."""

from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from psycopg import errors

from app.repositories import facturacion_repository as repo
from app.services.cotizacion_envio import CotizacionImposible


ENTREGA = datetime(2026, 10, 20, 15, 0, tzinfo=timezone.utc)
HOY = date(2026, 10, 30)

REGLA = (31, 2)  # id_regla, versión
COMPONENTES = [
    (1, "BASE", None, "ENVIO", "FIJO", Decimal("1000")),
    (2, "TRANSPORTE", "Terrestre", "TRAMO", "FIJO", Decimal("5000")),
    (3, "TRANSPORTE", "Marítimo", "TRAMO", "FIJO", Decimal("20000")),
    (4, "TRANSPORTE", "Aéreo", "TRAMO", "FIJO", Decimal("40000")),
]
TRAMOS = [
    (10, "Terrestre", "Buenos Aires", "Rosario"),
    (11, "Marítimo", "Rosario", "Montevideo"),
]


def crear_conexion_mock(cursor):
    conexion = MagicMock()
    conexion.__enter__.return_value = conexion
    conexion.cursor.return_value.__enter__.return_value = cursor
    return conexion


def cursor_emision(envio=None, factura_previa=None, tramos=TRAMOS,
                   regla=REGLA, cuenta=("ARS",), id_factura=900):
    """Respuestas en el orden en que emitir_factura_envio consulta."""
    cursor = MagicMock()
    cursor.rowcount = 1
    cursor.fetchone.side_effect = [
        envio if envio is not None else
        (7, "Entregado", ENTREGA, date(2026, 10, 20), "ACTIVO", HOY),
        factura_previa,
        regla,
        cuenta,
        (id_factura,),
    ]
    # Primero se leen los componentes de la regla y después los tramos.
    cursor.fetchall.side_effect = [list(COMPONENTES), list(tramos)]
    return cursor


def sentencias(cursor):
    return [(c.args[0], c.args[1] if len(c.args) > 1 else None)
            for c in cursor.execute.call_args_list]


def emitir(cursor, **kwargs):
    with patch.object(repo, "get_postgres_connection",
                      return_value=crear_conexion_mock(cursor)):
        return repo.emitir_factura_envio(45, **kwargs)


def test_emision_factura_envio_con_detalle_saldo_y_movimiento_por_total_con_iva():
    cursor = cursor_emision()
    factura = emitir(cursor)

    # 1000 + 5000 + 20000 = 26000 neto; IVA 5460; total 31460.
    assert factura["id_factura"] == 900
    assert (factura["neto"], factura["iva"], factura["total"]) == (
        Decimal("26000.00"), Decimal("5460.00"), Decimal("31460.00"))

    ejecutadas = sentencias(cursor)
    insert = next(p for sql, p in ejecutadas if "INSERT INTO factura (" in sql)
    # cliente, emisión, total, origen, moneda, envío, regla, neto, IVA, tasa,
    # tratamiento, fecha de entrega
    assert insert[0] == 7 and insert[1] == HOY
    assert insert[2] == Decimal("31460.00")
    assert insert[3] == "ENVIO_MANUAL" and insert[4] == "ARS"
    assert insert[5] == 45 and insert[6] == 31
    assert (insert[7], insert[8]) == (Decimal("26000.00"), Decimal("5460.00"))
    assert insert[9] == Decimal("0.21") and insert[10] == "IVA_21"
    assert insert[11] == ENTREGA

    detalle = [p for sql, p in ejecutadas if "INSERT INTO factura_detalle" in sql]
    assert [(d[1], d[2], d[3], d[6]) for d in detalle] == [
        (1, "BASE", None, Decimal("1000.00")),
        (2, "TRAMO", 10, Decimal("5000.00")),
        (3, "TRAMO", 11, Decimal("20000.00")),
    ]

    saldo = next(p for sql, p in ejecutadas if "SET saldo = saldo + %s" in sql)
    assert saldo == (Decimal("31460.00"), 7)

    mov_sql, mov = next((sql, p) for sql, p in ejecutadas
                        if "INSERT INTO movimiento_cuenta_corriente" in sql)
    assert "'FACTURA'" in mov_sql
    assert mov[:5] == (7, "ARS", Decimal("31460.00"), HOY, "900")
    assert "envio=45" in mov[5]


def test_emision_automatica_marca_su_origen():
    cursor = cursor_emision()
    emitir(cursor, origen="ENVIO_AUTOMATICA")
    insert = next(p for sql, p in sentencias(cursor) if "INSERT INTO factura (" in sql)
    assert insert[3] == "ENVIO_AUTOMATICA"


def test_origen_invalido_se_rechaza_sin_tocar_la_base():
    cursor = MagicMock()
    with pytest.raises(ValueError, match="Origen"):
        emitir(cursor, origen="MANUAL")
    cursor.execute.assert_not_called()


@pytest.mark.parametrize("envio, texto", [
    (None, "no existe"),
    ((7, "En tránsito", None, None, "ACTIVO", HOY), "no está Entregado"),
    ((7, "Entregado", None, None, "ACTIVO", HOY), "fecha real de entrega"),
    ((7, "Entregado", ENTREGA, date(2026, 10, 20), "INACTIVO", HOY), "cliente no está activo"),
    ((7, "Entregado", ENTREGA, date(2026, 10, 31), "ACTIVO", HOY), "anterior a la entrega"),
])
def test_envio_no_facturable_no_escribe(envio, texto):
    cursor = MagicMock()
    cursor.fetchone.side_effect = [envio]
    with pytest.raises(ValueError, match=texto):
        emitir(cursor)
    # Solo hubo la lectura con bloqueo: ninguna escritura.
    assert len(sentencias(cursor)) == 1
    assert not any("INSERT" in sql or "SET saldo" in sql for sql, _ in sentencias(cursor))


def test_envio_ya_facturado_no_duplica():
    cursor = cursor_emision(factura_previa=(812,))
    with pytest.raises(repo.FacturaExistente, match="812"):
        emitir(cursor)
    assert not any("INSERT" in sql for sql, _ in sentencias(cursor))


def test_carrera_con_indice_unico_se_informa_como_ya_facturado():
    cursor = cursor_emision()
    original = cursor.execute.side_effect

    def ejecutar(sql, params=None):
        if "INSERT INTO factura (" in sql:
            raise errors.UniqueViolation("uq_factura_original_envio")
        return original

    cursor.execute.side_effect = ejecutar
    with pytest.raises(repo.FacturaExistente, match="ya fue facturado"):
        emitir(cursor)


def test_envio_sin_tramos_no_se_factura():
    cursor = cursor_emision(tramos=[])
    with pytest.raises(CotizacionImposible, match="tramos"):
        emitir(cursor)
    assert not any("INSERT" in sql for sql, _ in sentencias(cursor))


def test_sin_tarifa_aprobada_no_se_factura():
    cursor = cursor_emision(regla=None)
    with pytest.raises(CotizacionImposible, match="tarifa estándar"):
        emitir(cursor)


def test_cuenta_sin_moneda_no_escribe():
    cursor = cursor_emision(cuenta=(None,))
    with pytest.raises(ValueError, match="moneda"):
        emitir(cursor)
    assert not any("INSERT INTO factura" in sql for sql, _ in sentencias(cursor))


def test_el_envio_y_el_cliente_se_bloquean_antes_de_emitir():
    cursor = cursor_emision()
    emitir(cursor)
    ejecutadas = [sql for sql, _ in sentencias(cursor)]
    assert "FOR UPDATE OF e, c" in ejecutadas[0]
    # La regla se bloquea para que no la reemplacen a mitad de la emisión.
    assert any("regla_tarifaria_version" in sql and "FOR SHARE" in sql
               for sql in ejecutadas)


def test_cotizar_solo_lee_sin_bloquear():
    cursor = MagicMock()
    cursor.fetchone.side_effect = [("En tránsito", "Cliente", False), REGLA]
    cursor.fetchall.side_effect = [list(COMPONENTES), list(TRAMOS)]
    with patch.object(repo, "get_postgres_connection",
                      return_value=crear_conexion_mock(cursor)):
        r = repo.cotizar_envio(45)
    assert r["total"] == Decimal("31460.00") and r["facturado"] is False
    assert not any("FOR " in sql for sql, _ in sentencias(cursor))


def test_envios_facturables_filtra_entregados_sin_factura_hasta_el_corte():
    cursor = MagicMock()
    cursor.fetchall.return_value = []
    with patch.object(repo, "get_postgres_connection",
                      return_value=crear_conexion_mock(cursor)):
        repo.listar_envios_facturables(fecha_corte=HOY, id_cliente=7)
    sql, params = cursor.execute.call_args.args
    assert "LOWER(BTRIM(e.estado)) = 'entregado'" in sql
    assert "NOT EXISTS" in sql and "f.id_envio = e.id_envio" in sql
    assert params == (HOY, "America/Argentina/Buenos_Aires", HOY, 7, 7)


def test_facturas_del_cliente_muestran_el_envio():
    cursor = MagicMock()
    cursor.fetchall.return_value = []
    with patch.object(repo, "get_postgres_connection",
                      return_value=crear_conexion_mock(cursor)):
        repo.listar_facturas_cliente(7)
    assert "f.id_envio" in cursor.execute.call_args.args[0]


def test_listado_muestra_origen_de_cada_factura():
    from app.services import facturacion_service as servicio
    historica = (1, HOY, Decimal("10"), "Pagada", Decimal("10"), Decimal("0"),
                 None, None, None, None)
    por_envio = (2, HOY, Decimal("12.10"), "Pendiente", Decimal("0"),
                 Decimal("12.10"), 45, Decimal("10"), Decimal("2.10"), "ENVIO_MANUAL")
    assert servicio.origen_factura(historica) == "Histórica (sin envío)"
    assert servicio.origen_factura(por_envio) == "Envío 45"
