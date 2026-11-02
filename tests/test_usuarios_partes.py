"""Usuarios de proveedor, de operador o internos (usuario.id_cliente NULL).

Verifica que login, sesión, listados, mensajería y filtros por cliente
funcionen igual que con usuarios de cliente.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.models.usuario import Usuario
from app.repositories import usuario_repository
from app.services import autenticacion
from app.services import mensajeria_service
from app.services import sesion_service
from app.services import trazabilidad_service
from app.services import usuario_service


def crear_conexion_mock(cursor):
    conexion = MagicMock()
    conexion.__enter__.return_value = conexion
    conexion.cursor.return_value.__enter__.return_value = cursor
    return conexion


FECHA = datetime(2026, 10, 30, tzinfo=timezone.utc)

# (id_cliente, id_proveedor, id_operador, nombre de la parte, texto esperado)
PARTES = [
    (4, None, None, "Alimentos del Norte", "Cliente: Alimentos del Norte"),
    (None, 2, None, "Seguros Rumbo", "Proveedor: Seguros Rumbo"),
    (None, None, 1, "Transportes Andinos", "Operador: Transportes Andinos"),
    (None, None, None, None, "Interno"),
]


# ------------------------------------------------------------ modelo

def test_modelo_rechaza_dos_partes():
    with pytest.raises(ValueError):
        Usuario(4, 2, "A", "B", "a@b.c", "h", "ACTIVO", id_proveedor=1)


@pytest.mark.parametrize("cli, prov, oper, _nombre, esperado", PARTES)
def test_modelo_acepta_cada_parte(cli, prov, oper, _nombre, esperado):
    usuario = Usuario(cli, 2, "A", "B", "a@b.c", "h", "ACTIVO",
                      id_proveedor=prov, id_operador=oper)
    assert "Parte:" in str(usuario)


@pytest.mark.parametrize("cli, prov, oper, _nombre, _esperado", PARTES)
def test_alta_guarda_la_parte(cli, prov, oper, _nombre, _esperado):
    cursor = MagicMock()
    cursor.fetchone.return_value = (10,)
    conexion = crear_conexion_mock(cursor)
    usuario = Usuario(cli, 2, "Ana", "Bo", "a@b.co", "h", "ACTIVO",
                      id_proveedor=prov, id_operador=oper)

    with patch.object(usuario_repository, "get_postgres_connection",
                      return_value=conexion):
        assert usuario_repository.crear_usuario(usuario) == 10

    params = cursor.execute.call_args.args[1]
    assert params[0] == cli
    assert params[-2:] == (prov, oper)


# ---------------------------------------------------------- listados

@pytest.mark.parametrize("cli, prov, oper, nombre, esperado", PARTES)
def test_mostrar_usuario_con_cualquier_parte(cli, prov, oper, nombre,
                                             esperado, capsys):
    fila = (5, cli, 2, "Ana", "Pérez", "ana@x.com", "ACTIVO", FECHA,
            prov, oper, nombre)
    usuario_service.mostrar_usuario(fila)
    salida = capsys.readouterr().out
    assert f"Parte: {esperado}" in salida
    assert "None" not in salida.split("Fecha")[0]


def test_mostrar_usuario_tolera_fila_vieja(capsys):
    fila = (5, 4, 2, "Ana", "Pérez", "ana@x.com", "ACTIVO", FECHA)
    usuario_service.mostrar_usuario(fila)
    assert "Parte: Cliente ID 4" in capsys.readouterr().out


def test_listado_usa_left_join_para_no_perder_usuarios():
    cursor = MagicMock()
    cursor.fetchall.return_value = []
    with patch.object(usuario_repository, "get_postgres_connection",
                      return_value=crear_conexion_mock(cursor)):
        usuario_repository.listar_usuarios()
    sql = cursor.execute.call_args.args[0]
    assert "LEFT JOIN cliente" in sql
    assert " JOIN cliente" not in sql.replace("LEFT JOIN cliente", "")


# ------------------------------------------------------- sesión y login

@pytest.mark.sesion_real
@pytest.mark.parametrize("cli, prov, oper, _nombre, _esperado", PARTES)
def test_sesion_actual_con_cualquier_parte(cli, prov, oper, _nombre, _esperado):
    cursor = MagicMock()
    cursor.fetchone.return_value = (
        70, 5, "Ana", "Pérez", "ana@x.com", "Usuario", 2, cli, prov, oper,
        False, False,       # expirada, registrar actividad (migración 016)
    )
    autenticacion.establecer_sesion(70, 5)
    try:
        with patch.object(autenticacion, "get_postgres_connection",
                          return_value=crear_conexion_mock(cursor)):
            sesion = autenticacion.obtener_sesion_actual()
            # Las funciones internas son solo para usuarios internos; los
            # externos usan su portal (test_portal_permisos.py).
            interno = (cli, prov, oper) == (None, None, None)
            assert autenticacion.verificar_permiso(1) is interno
    finally:
        autenticacion.limpiar_sesion()

    assert sesion["id_usuario"] == 5
    assert (sesion["id_cliente"], sesion["id_proveedor"],
            sesion["id_operador"]) == (cli, prov, oper)
    # El control de sesión no exige cliente.
    sql = cursor.execute.call_args.args[0]
    assert "id_cliente IS NOT NULL" not in sql


def test_login_no_depende_del_cliente():
    usuario = (5, "Ana", "Pérez", "ana@x.com", "hash", "ACTIVO", "Usuario", 2, False, 1, False)
    with patch.object(sesion_service, "obtener_sesion_actual", return_value=None), \
         patch.object(sesion_service, "registrar_ingreso_correcto"), \
         patch.object(sesion_service, "buscar_usuario_por_email", return_value=usuario), \
         patch.object(sesion_service, "verificar_contrasena", return_value=True), \
         patch.object(sesion_service, "iniciar_sesion_db", return_value=70), \
         patch.object(sesion_service, "establecer_sesion") as establecer, \
         patch("builtins.input", return_value="ana@x.com"), \
         patch.object(sesion_service, "getpass", return_value="x"):
        sesion_service.iniciar_sesion_service()
    establecer.assert_called_once_with(70, 5)


# ---------------------------------------------------------- mensajería

@pytest.mark.parametrize("_cli, _prov, _oper, _nombre, esperado", PARTES)
def test_mensajeria_muestra_la_parte(_cli, _prov, _oper, _nombre, esperado):
    fila = (5, "Ana", "Pérez", "ana@x.com", esperado)
    assert mensajeria_service.describir_usuario(fila).endswith(f"- {esperado}")


def test_mensajeria_tolera_fila_sin_parte():
    fila = (5, "Ana", "Pérez", "ana@x.com")
    assert mensajeria_service.describir_usuario(fila) == "Ana Pérez (ana@x.com)"


def test_mensajeria_lista_usuarios_sin_cliente():
    from app.repositories import mensajeria_repository
    cursor = MagicMock()
    cursor.fetchall.return_value = []
    with patch.object(mensajeria_repository, "get_postgres_connection",
                      return_value=crear_conexion_mock(cursor)):
        mensajeria_repository.obtener_usuarios_activos()
    sql = cursor.execute.call_args.args[0]
    assert "LEFT JOIN cliente" in sql
    assert "ELSE 'Interno'" in sql


# ----------------------------------------------------- filtro por cliente

def test_usuario_de_cliente_queda_restringido_a_su_cliente():
    sesion = {"nivel_permisos": 2, "id_cliente": 4,
              "id_proveedor": None, "id_operador": None}
    assert trazabilidad_service.cliente_visible(sesion) == 4


@pytest.mark.parametrize("nivel", [1, 3, 5])
def test_usuario_de_cliente_restringido_sin_importar_el_nivel(nivel):
    sesion = {"nivel_permisos": nivel, "id_cliente": 4,
              "id_proveedor": None, "id_operador": None}
    assert trazabilidad_service.cliente_visible(sesion) == 4


@pytest.mark.parametrize("nivel", [1, 3, 5])
def test_usuario_interno_ve_todo_sin_importar_el_nivel(nivel):
    sesion = {"nivel_permisos": nivel, "id_cliente": None,
              "id_proveedor": None, "id_operador": None}
    assert trazabilidad_service.cliente_visible(sesion) is None


@pytest.mark.parametrize("nivel", [1, 5])
@pytest.mark.parametrize("prov, oper", [(2, None), (None, 1)])
def test_proveedor_u_operador_no_ven_datos_de_clientes(prov, oper, nivel):
    sesion = {"nivel_permisos": nivel, "id_cliente": None,
              "id_proveedor": prov, "id_operador": oper}
    with pytest.raises(PermissionError):
        trazabilidad_service.cliente_visible(sesion)


def test_sin_sesion_no_hay_acceso():
    with pytest.raises(PermissionError):
        trazabilidad_service.cliente_visible(None)
