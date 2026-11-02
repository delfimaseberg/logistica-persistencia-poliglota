
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
