"""Las pruebas unitarias no se conectan a ninguna base de datos.

Toda conexión real (PostgreSQL vía psycopg o cualquier socket de red: MongoDB,
Cassandra, Neo4j) se bloquea y se registra. Si una prueba lo intenta, falla,
aunque el código haya atrapado el error. Las pruebas de integración
(tests/integration, con INTEGRATION_TESTS=1) quedan fuera de esta barrera.
"""

import os
import socket

import psycopg
import pytest


class ConexionRealEnTestUnitario(RuntimeError):
    pass


@pytest.fixture(autouse=True)
def sin_bases_de_datos(request, monkeypatch):
    if "integration" in str(request.node.fspath) or os.getenv("INTEGRATION_TESTS") == "1":
        yield
        return

    intentos = []

    def bloquear(nombre):
        def _bloqueado(*args, **kwargs):
            intentos.append(nombre)
            raise ConexionRealEnTestUnitario(f"Conexión real a {nombre} en un test unitario")
        return _bloqueado

    monkeypatch.setattr(psycopg.Connection, "connect", classmethod(
        lambda cls, *a, **k: bloquear("PostgreSQL")()))
    monkeypatch.setattr(socket.socket, "connect", bloquear("la red (socket.connect)"))
    monkeypatch.setattr(socket.socket, "connect_ex", bloquear("la red (socket.connect_ex)"))
    monkeypatch.setattr(socket, "create_connection", bloquear("la red (create_connection)"))
    yield
    assert not intentos, f"El test intentó conectarse a: {sorted(set(intentos))}"
