from decimal import Decimal

from app.repositories import tarifas_repository


class CursorFalso:
    def __init__(self, respuestas):
        self.respuestas = iter(respuestas)
        self.sql = []
        self.parametros = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql, params=None):
        self.sql.append(" ".join(sql.split()))
        self.parametros.append(params)

    def fetchone(self):
        return next(self.respuestas)


class ConexionFalsa:
    def __init__(self, cursor):
        self._cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def cursor(self):
        return self._cursor


def test_aprobar_tarifa_no_sobrescribe_el_snapshot_aprobado(monkeypatch):
    cursor = CursorFalso([
        (12, Decimal("20.00"), "BORRADOR", 33),  # tarifa en revisión
        ("TST",),                                 # moneda de la cuenta
        None,                                      # factura vinculada a borrador
        None,                                      # otra tarifa aprobada
        None,                                      # RETURNING no utilizado
        None,
    ])
    monkeypatch.setattr(
        tarifas_repository, "get_postgres_connection",
        lambda: ConexionFalsa(cursor),
    )
    tarifas_repository.aprobar_tarifa(
        91,
        {"importe_impuestos": Decimal("0.00"), "importe_total": Decimal("20.00"),
         "moneda": "TST", "id_configuracion_fiscal": 4,
         "tratamiento_impositivo": "TEST", "tasa_impositiva": None},
        7,
        "aprobación sintética de test",
    )
    update = next(sql for sql in cursor.sql if sql.startswith("UPDATE tarifa_envio"))
    assert "id_regla" not in update
    assert "detalle_calculo" not in update
    assert "importe_base" not in update
    assert any(sql.startswith("INSERT INTO tarifa_envio_auditoria") for sql in cursor.sql)


def test_reemplazo_solo_actualiza_estado_y_registra_auditoria_en_la_transaccion(monkeypatch):
    cursor = CursorFalso([("APROBADA",)])
    monkeypatch.setattr(
        tarifas_repository, "get_postgres_connection",
        lambda: ConexionFalsa(cursor),
    )
    tarifas_repository.reemplazar_tarifa_aprobada(91, 7, "reemplazo respaldado")
    insert_index = next(i for i, sql in enumerate(cursor.sql)
                        if sql.startswith("INSERT INTO tarifa_envio_auditoria"))
    update_index = next(i for i, sql in enumerate(cursor.sql)
                        if sql.startswith("UPDATE tarifa_envio"))
    assert insert_index < update_index
    update = cursor.sql[update_index]
    assert "SET estado = 'REEMPLAZADA'" in update
    assert "importe_" not in update
    assert "detalle_calculo" not in update
    assert "id_transaccion" in cursor.sql[insert_index]


def test_reemplazo_exige_actor_y_motivo():
    import pytest

    with pytest.raises(ValueError, match="usuario y motivo"):
        tarifas_repository.reemplazar_tarifa_aprobada(91, 7, " ")


def test_aprobacion_de_nueva_version_audita_reemplazo_antes_del_estado(monkeypatch):
    cursor = CursorFalso([("TEST", "BORRADOR"), (1,), (14,)])
    monkeypatch.setattr(
        tarifas_repository, "get_postgres_connection",
        lambda: ConexionFalsa(cursor),
    )
    tarifas_repository.aprobar_regla(20, 7, "aprobación documentada")
    replacement_audit = next(
        i for i, (sql, params) in enumerate(zip(cursor.sql, cursor.parametros))
        if sql.startswith("INSERT INTO regla_tarifaria_auditoria")
        and params[1] == "Reemplazada por versión 20"
    )
    replacement_update = next(
        i for i, sql in enumerate(cursor.sql)
        if sql.startswith("UPDATE regla_tarifaria_version SET estado = 'REEMPLAZADA'")
    )
    approval_audit = next(
        i for i, (sql, params) in enumerate(zip(cursor.sql, cursor.parametros))
        if sql.startswith("INSERT INTO regla_tarifaria_auditoria")
        and params[1] == "aprobación documentada"
    )
    approval_update = next(
        i for i, sql in enumerate(cursor.sql)
        if sql.startswith("UPDATE regla_tarifaria_version SET estado = 'APROBADA'")
    )
    assert replacement_audit < replacement_update < approval_audit < approval_update
