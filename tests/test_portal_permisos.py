"""Acceso por parte: portal del cliente/operador/proveedor, funciones
internas bloqueadas para externos y mensajería filtrada."""

from contextlib import ExitStack
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from app.repositories import mensajeria_repository
from app.services import autenticacion
from app.services import facturacion_service
from app.services import mensajeria_service
from app.services import portal_service
from app.services import terceros_service
from app.ui import menu_mensajeria, menu_principal, menu_portal


def sesion(cli=None, prov=None, oper=None, nivel=2, id_usuario=50):
    return {"id_sesion": 1, "id_usuario": id_usuario, "nombre": "Ana", "apellido": "P",
            "email": "a@x", "rol": "Usuario", "nivel_permisos": nivel,
            "id_cliente": cli, "id_proveedor": prov, "id_operador": oper}


INTERNO = sesion(nivel=5)
CLIENTE = sesion(cli=7)
CLIENTE_NIVEL5 = sesion(cli=7, nivel=5)
OPERADOR = sesion(oper=3)
PROVEEDOR = sesion(prov=2)


def con_sesion(s):
    """La sesión simulada vale en todos los módulos que la consultan."""
    pila = ExitStack()
    for modulo in (autenticacion, portal_service, mensajeria_service, menu_portal):
        pila.enter_context(patch.object(modulo, "obtener_sesion_actual", return_value=s))
    return pila


# ------------------------------------------------------------- parte

@pytest.mark.parametrize("s, esperado", [
    (INTERNO, ("INTERNO", None)), (CLIENTE, ("CLIENTE", 7)),
    (OPERADOR, ("OPERADOR", 3)), (PROVEEDOR, ("PROVEEDOR", 2)), (None, (None, None)),
])
def test_parte_de_la_sesion(s, esperado):
    assert autenticacion.parte_de(s) == esperado


@pytest.mark.parametrize("s", [CLIENTE, CLIENTE_NIVEL5, OPERADOR, sesion(prov=2, nivel=5)])
def test_externos_no_acceden_a_funciones_internas_ni_con_nivel_5(s, capsys):
    with con_sesion(s):
        assert autenticacion.verificar_permiso(1) is False
    assert "no disponible" in capsys.readouterr().out


def test_interno_sigue_dependiendo_del_nivel():
    with con_sesion(sesion(nivel=2)):
        assert autenticacion.verificar_permiso(1) is True
        assert autenticacion.verificar_permiso(3) is False
    with con_sesion(INTERNO):
        assert autenticacion.verificar_permiso(5) is True


def test_verificar_sesion_vale_para_cualquier_parte():
    for s in (INTERNO, CLIENTE, OPERADOR, PROVEEDOR):
        with con_sesion(s):
            assert autenticacion.verificar_sesion() is True
    with con_sesion(None):
        assert autenticacion.verificar_sesion() is False


@pytest.mark.parametrize("funcion", [
    facturacion_service.emitir_factura_service,
    facturacion_service.facturacion_automatica_service,
    facturacion_service.registrar_pago_service,
    facturacion_service.precios_transporte_service,
    facturacion_service.apertura_cuenta_service,
    facturacion_service.cierre_mensual_service,
])
@pytest.mark.parametrize("s", [CLIENTE_NIVEL5, OPERADOR, PROVEEDOR])
def test_operaciones_de_facturacion_bloqueadas_para_externos(funcion, s, capsys):
    with con_sesion(s), patch("builtins.input", side_effect=AssertionError("no debe pedir datos")):
        assert funcion() is None
    assert "no disponible para usuarios de clientes" in capsys.readouterr().out


@pytest.mark.parametrize("nombre", [
    "registrar_factura_recibida_service", "registrar_pago_emitido_service",
    "asignar_operador_tramo_service",
])
def test_operaciones_de_terceros_bloqueadas_para_externos(nombre, capsys):
    funcion = getattr(terceros_service, nombre)
    args = ("OPERADOR",) if "factura" in nombre or "pago" in nombre else ()
    with con_sesion(OPERADOR), patch("builtins.input", side_effect=AssertionError):
        assert funcion(*args) is None
    assert "no disponible para usuarios de clientes" in capsys.readouterr().out


# ------------------------------------------------------------- menús

def test_menu_segun_la_parte():
    assert menu_principal.menu_para(INTERNO) is menu_principal.mostrar_menu_interno
    for s in (CLIENTE, CLIENTE_NIVEL5, OPERADOR, PROVEEDOR):
        assert menu_principal.menu_para(s) is menu_portal.mostrar_portal


def test_menu_interno_renumerado_con_facturacion_y_reportes_separados():
    textos = {k: v[0] for k, v in menu_principal.OPCIONES_INTERNAS.items()}
    assert textos["9"] == "Facturación y cobranzas"
    assert textos["10"] == "Reportes"
    assert textos["12"] == "Proveedores" and textos["13"] == "Operadores logísticos"
    assert menu_principal.OPCION_CERRAR_SESION == "15"
    assert menu_principal.OPCION_CAMBIAR_CONTRASENA == "14"


def test_reportes_salieron_de_facturacion():
    from app.ui import menu_facturacion, menu_reportes
    from app.services import reportes_pantallas
    en_facturacion = {v[1] for v in menu_facturacion.OPCIONES.values()}
    en_reportes = {v[1] for v in menu_reportes.OPCIONES.values()}
    assert facturacion_service.reporte_facturacion_service in en_reportes
    assert facturacion_service.reporte_ingresos_service in en_reportes
    assert not en_facturacion & en_reportes
    # "Envíos por estado" está en el submenú de reportes operativos.
    operativos = [v[0] for v in reportes_pantallas.REPORTES_OPERATIVOS.values()]
    assert "Envíos por estado" in operativos


def test_portal_del_cliente_no_tiene_operaciones_de_escritura():
    funciones = {v[1] for v in menu_portal.OPCIONES_CLIENTE.values()}
    for prohibida in (facturacion_service.emitir_factura_service,
                      facturacion_service.registrar_pago_service,
                      facturacion_service.cierre_mensual_service):
        assert prohibida not in funciones


def test_portal_de_proveedor_no_tiene_tramos():
    textos = [v[0] for v in menu_portal.OPCIONES_PROVEEDOR.values()]
    assert not any("tramos" in t.lower() for t in textos)


def test_portal_se_cierra_si_cambia_la_sesion():
    with con_sesion(None), patch("builtins.input", side_effect=AssertionError):
        assert menu_portal.mostrar_portal(CLIENTE) is False


# --------------------------------------------- portal: solo lo propio

ENVIO_PROPIO = (21, 7, "Viñedos", "Mendoza", "Santiago", "Entregado", "Media",
                datetime(2026, 10, 1, tzinfo=timezone.utc), None)
ENVIO_AJENO = (22, 9, "Otro", "A", "B", "En tránsito", "Media",
               datetime(2026, 10, 1, tzinfo=timezone.utc), None)


def test_mis_envios_usa_el_cliente_de_la_sesion(capsys):
    listar = MagicMock(return_value=[])
    with con_sesion(CLIENTE), patch.object(portal_service, "listar_envios_cliente", listar), \
         patch("builtins.input", return_value=""):
        portal_service.mis_envios_service()
    listar.assert_called_once_with(7)


@pytest.mark.parametrize("servicio", ["seguimiento_envio_service", "eventos_envio_service",
                                      "ruta_envio_service"])
def test_envio_ajeno_responde_que_no_existe(servicio, capsys):
    vista = MagicMock()
    nombre_vista = {"seguimiento_envio_service": "seguimiento_temporal_service",
                    "eventos_envio_service": "historial_envio_service",
                    "ruta_envio_service": "ruta_completa_service"}[servicio]
    with con_sesion(CLIENTE), \
         patch.object(portal_service, "buscar_envio_por_id", return_value=ENVIO_AJENO), \
         patch.object(portal_service.trazabilidad_service, nombre_vista, vista), \
         patch("builtins.input", side_effect=["22", ""]):
        getattr(portal_service, servicio)()
    vista.assert_not_called()
    assert portal_service.NO_EXISTE_ENVIO in capsys.readouterr().out


def test_envio_propio_se_muestra_sin_volver_a_pedirlo():
    vista = MagicMock()
    with con_sesion(CLIENTE), \
         patch.object(portal_service, "buscar_envio_por_id", return_value=ENVIO_PROPIO), \
         patch.object(portal_service.trazabilidad_service, "seguimiento_temporal_service", vista), \
         patch("builtins.input", side_effect=["21"]):
        portal_service.seguimiento_envio_service()
    vista.assert_called_once_with(ENVIO_PROPIO)


def detalle(id_cliente):
    return {"id_factura": 30, "id_cliente": id_cliente, "cliente": "X",
            "fecha_emision": date(2026, 10, 30), "id_envio": 21, "id_reporte": None,
            "neto": Decimal("100"), "iva": Decimal("21"), "tasa_iva": Decimal("0.21"),
            "total": Decimal("121"), "estado": "Pendiente", "origen_emision": "ENVIO_MANUAL",
            "id_regla": 1, "fecha_entrega": None, "moneda": "ARS", "lineas": []}


def test_factura_ajena_responde_que_no_existe(capsys):
    with con_sesion(CLIENTE), \
         patch.object(portal_service, "obtener_detalle_factura", return_value=detalle(9)), \
         patch("builtins.input", side_effect=["30", ""]):
        portal_service.detalle_mi_factura_service()
    salida = capsys.readouterr().out
    assert portal_service.NO_EXISTE_FACTURA in salida
    assert "TOTAL" not in salida


def test_factura_propia_se_muestra(capsys):
    with con_sesion(CLIENTE), \
         patch.object(portal_service, "obtener_detalle_factura", return_value=detalle(7)), \
         patch("builtins.input", side_effect=["30", ""]):
        portal_service.detalle_mi_factura_service()
    assert "TOTAL" in capsys.readouterr().out


def test_mis_facturas_y_cuenta_solo_del_cliente_de_la_sesion():
    listar, cuenta = MagicMock(return_value=[]), MagicMock()
    with con_sesion(CLIENTE), patch.object(portal_service, "listar_facturas_cliente", listar), \
         patch.object(portal_service, "mostrar_cuenta_cliente", cuenta), \
         patch("builtins.input", return_value=""):
        portal_service.mis_facturas_service()
        portal_service.mi_cuenta_corriente_service()
    listar.assert_called_once_with(7)
    cuenta.assert_called_once_with(7)


def test_opciones_del_cliente_rechazan_otras_partes(capsys):
    listar = MagicMock()
    with con_sesion(OPERADOR), patch.object(portal_service, "listar_envios_cliente", listar), \
         patch("builtins.input", return_value=""):
        portal_service.mis_envios_service()
    listar.assert_not_called()
    assert "no corresponde" in capsys.readouterr().out


def test_cuenta_de_tercero_usa_su_propia_parte():
    consultar = MagicMock(return_value=None)
    with con_sesion(PROVEEDOR), \
         patch.object(portal_service.cuentas, "consultar_cuenta_tercero", consultar), \
         patch("builtins.input", return_value=""):
        portal_service.mi_cuenta_tercero_service()
    consultar.assert_called_once_with("PROVEEDOR", 2)


def test_tramos_solo_para_operadores():
    listar = MagicMock(return_value=[])
    with con_sesion(OPERADOR), patch.object(portal_service, "listar_tramos_operador", listar), \
         patch("builtins.input", return_value=""):
        portal_service.mis_tramos_service()
    listar.assert_called_once_with(3)
    listar.reset_mock()
    with con_sesion(PROVEEDOR), patch.object(portal_service, "listar_tramos_operador", listar), \
         patch("builtins.input", return_value=""):
        portal_service.mis_tramos_service()
    listar.assert_not_called()


# ------------------------------------------------------------ mensajería

def crear_conexion_mock(cursor):
    conexion = MagicMock()
    conexion.__enter__.return_value = conexion
    conexion.cursor.return_value.__enter__.return_value = cursor
    return conexion


def consulta_destinatarios(tipo, id_parte):
    cursor = MagicMock()
    cursor.fetchall.return_value = []
    with patch.object(mensajeria_repository, "get_postgres_connection",
                      return_value=crear_conexion_mock(cursor)):
        mensajeria_repository.obtener_destinatarios_permitidos(50, tipo, id_parte)
    return cursor.execute.call_args.args


def test_consulta_de_destinatarios_por_parte():
    sql, params = consulta_destinatarios("CLIENTE", 7)
    assert params == {"yo": 50, "tipo": "CLIENTE", "id": 7}
    assert "u.id_usuario <> %(yo)s" in sql
    # Internos, mismo cliente y operadores de SUS envíos.
    assert "num_nonnulls(u.id_cliente, u.id_proveedor,\n                                      u.id_operador) = 0" in sql
    assert "u.id_cliente = %(id)s" in sql
    assert "WHERE e.id_cliente = %(id)s" in sql
    # Operador: clientes cuyos envíos transportó.
    assert "WHERE t.id_operador = %(id)s" in sql
    assert "u.estado = 'ACTIVO'" in sql


def fila(id_usuario, parte):
    return (id_usuario, "Nom", "Ape", f"u{id_usuario}@x", parte)


def test_destinatarios_usa_la_parte_de_la_sesion():
    consulta = MagicMock(return_value=[fila(4, "Interno")])
    with patch.object(mensajeria_service, "obtener_sesion_actual", return_value=CLIENTE), \
         patch.object(mensajeria_service, "obtener_destinatarios_permitidos", consulta):
        mensajeria_service.destinatarios_para_sesion()
    consulta.assert_called_once_with(50, "CLIENTE", 7)


def test_no_se_puede_enviar_a_un_destinatario_no_permitido():
    with patch.object(mensajeria_service, "obtener_sesion_actual", return_value=CLIENTE), \
         patch.object(mensajeria_service, "obtener_destinatarios_permitidos",
                      return_value=[fila(4, "Interno"), fila(6, "Operador: Andinos")]):
        mensajeria_service.validar_destinatario(6)
        with pytest.raises(PermissionError):
            mensajeria_service.validar_destinatario(99)


def test_enviar_mensaje_no_registra_si_el_destinatario_no_esta_permitido(capsys):
    registrar = MagicMock()
    with patch.object(mensajeria_service, "obtener_sesion_actual", return_value=CLIENTE), \
         patch.object(mensajeria_service, "seleccionar_usuario", return_value=fila(99, "Cliente: Otro")), \
         patch.object(mensajeria_service, "obtener_destinatarios_permitidos",
                      return_value=[fila(4, "Interno")]), \
         patch.object(mensajeria_service, "registrar_mensaje_privado", registrar), \
         patch("builtins.input", return_value=""):
        mensajeria_service.enviar_mensaje_service()
    registrar.assert_not_called()
    assert "No podés enviar" in capsys.readouterr().out


def test_externos_no_ven_emails():
    fila_u = fila(4, "Interno")
    assert "@" not in mensajeria_service.describir_usuario(fila_u, mostrar_email=False)
    assert "@" in mensajeria_service.describir_usuario(fila_u, mostrar_email=True)
    with patch.object(mensajeria_service, "obtener_sesion_actual", return_value=CLIENTE):
        assert mensajeria_service.puede_ver_emails() is False
    with patch.object(mensajeria_service, "obtener_sesion_actual", return_value=INTERNO):
        assert mensajeria_service.puede_ver_emails() is True


@pytest.mark.parametrize("s", [CLIENTE, OPERADOR, PROVEEDOR])
def test_externos_no_crean_grupos_ni_agregan_miembros(s, capsys):
    crear, agregar = MagicMock(), MagicMock()
    with patch.object(mensajeria_service, "obtener_sesion_actual", return_value=s), \
         patch.object(mensajeria_service, "crear_grupo", crear), \
         patch.object(mensajeria_service, "agregar_miembro_grupo", agregar), \
         patch("builtins.input", return_value=""):
        mensajeria_service.crear_grupo_service()
        mensajeria_service.agregar_miembro_service()
    crear.assert_not_called()
    agregar.assert_not_called()
    assert "Solo los usuarios internos" in capsys.readouterr().out


def test_menu_de_mensajeria_oculta_administracion_de_grupos_a_externos():
    externos = menu_mensajeria.opciones_para(CLIENTE)
    internos = menu_mensajeria.opciones_para(INTERNO)
    textos_externos = [texto for texto, _, _ in externos.values()]
    assert not any("Crear grupo" in t or "Agregar miembro" in t or "administrados" in t
                   for t in textos_externos)
    assert {"Enviar mensaje privado", "Enviar mensaje a grupo",
            "Consultar mensajes de grupo"} <= set(textos_externos)
    assert set(internos) == set(menu_mensajeria.OPCIONES)


def test_menu_de_mensajeria_numera_consecutivo_para_externos():
    externos = menu_mensajeria.opciones_para(CLIENTE)
    assert list(externos) == [str(i) for i in range(1, len(externos) + 1)]
    assert externos["7"][0] == "Enviar mensaje a grupo"
    assert externos["8"][0] == "Consultar mensajes de grupo"
