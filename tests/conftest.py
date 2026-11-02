"""Las pruebas unitarias no se conectan a ninguna base de datos.

Toda conexión real (PostgreSQL vía psycopg o cualquier socket de red: MongoDB,
Cassandra, Neo4j) se bloquea y se registra. Si una prueba lo intenta, falla,
aunque el código haya atrapado el error. Las pruebas de integración
(tests/integration, con INTEGRATION_TESTS=1) quedan fuera de esta barrera.
"""

import os
import socket
import tempfile

# Antes de importar la aplicación: los logs de los tests van a una carpeta
# temporal, no a logs/app.log (que es el log real de la aplicación).
os.environ.setdefault("LOGS_DIR", tempfile.mkdtemp(prefix="logs_tests_"))

import psycopg  # noqa: E402
import pytest  # noqa: E402


class ConexionRealEnTestUnitario(RuntimeError):
    pass


# Sesión interna (administrador) que ven los servicios cuando el test no
# simula otra: desde la migración 016 cada servicio verifica el permiso por sí
# mismo. Los tests que prueban la sesión real se marcan con @pytest.mark.sesion_real;
# los que simulan otra parte la parchean ellos mismos (eso tiene prioridad).
SESION_INTERNA_DE_PRUEBA = {
    "id_sesion": 1, "id_usuario": 4, "nombre": "Admin", "apellido": "Pruebas",
    "email": "admin@pruebas.example", "rol": "Administrador", "nivel_permisos": 5,
    "id_cliente": None, "id_proveedor": None, "id_operador": None,
}


@pytest.fixture(autouse=True)
def sesion_interna_por_defecto(request, monkeypatch):
    if "integration" in str(request.node.fspath) or request.node.get_closest_marker("sesion_real"):
        yield
        return
    from app.services import autenticacion
    monkeypatch.setattr(autenticacion, "obtener_sesion_actual",
                        lambda: dict(SESION_INTERNA_DE_PRUEBA))
    yield


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
