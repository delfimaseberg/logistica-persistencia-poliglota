"""Seguridad: política de contraseñas, bloqueo, inactividad, permisos,
validaciones de datos y consultas parametrizadas (migración 016)."""

import ast
import importlib
import inspect
import logging
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.services import autenticacion, contrasena_service, sesion_service, usuario_service
from app.utils import politica_contrasena as politica
from app.utils import validaciones_datos as v
from app.utils.seguridad import generar_hash_contrasena, verificar_contrasena

VALIDA = "Mesa#Roja2026"
CLAVE_TEST = "NoLaGuardes!77"


def conexion_mock(cursor):
    conexion = MagicMock()
    conexion.__enter__.return_value = conexion
    conexion.cursor.return_value.__enter__.return_value = cursor
    return conexion


def sesion(nivel=5, **parte):
    base = {"id_sesion": 30, "id_usuario": 4, "nombre": "Ana", "apellido": "Gómez",
            "email": "ana@empresa.example", "rol": "Administrador", "nivel_permisos": nivel,
            "id_cliente": None, "id_proveedor": None, "id_operador": None}
    base.update(parte)
    return base


# ------------------------------------------------------------ 1. política

@pytest.mark.parametrize("clave, regla", [
    ("Ab1#xyz", "al menos 8 caracteres"),
    ("mesa#roja2026", "una mayúscula"),
    ("MESA#ROJA2026", "una minúscula"),
    ("Mesa#RojaAzul", "un número"),
    ("MesaRoja2026", "un símbolo"),
    ("Mesa #Roja2026", "no tener espacios"),
    ("A1#" + "a" * 126, "como máximo 128"),
])
def test_cada_regla_de_la_politica(clave, regla):
    with pytest.raises(ValueError, match=regla):
        politica.validar_politica(clave)


def test_no_puede_contener_email_nombre_ni_apellido():
    for clave in ("Delfina#2026", "GARCIA#2026x", "delfi.na#2026X", "García!2026a"):
        errores = politica.errores_politica(clave, "delfina@gmail.com", "Delfina", "García")
        assert "no contener tu email, nombre ni apellido" in errores, clave
    # partes cortas (menos de 3 letras) no cuentan
    assert politica.errores_politica("Lu#Casa2026", "lu@x.example", "Lu", "Li") == []


def test_una_contrasena_valida_pasa_y_se_informan_todas_las_reglas_juntas():
    assert politica.validar_politica(VALIDA, "ana@x.example", "Ana", "Gómez") == VALIDA
    with pytest.raises(ValueError) as error:
        politica.validar_politica("abc")
    texto = str(error.value)
    assert "8 caracteres" in texto and "mayúscula" in texto and "número" in texto and "símbolo" in texto


def test_las_contrasenas_guardadas_no_se_revalidan():
    # Una contraseña vieja que no cumple la política sigue verificando con su hash.
    viejo = generar_hash_contrasena("1234")
    assert verificar_contrasena("1234", viejo)


# ------------------------------------------------------------ 2. alta oculta y con confirmación

def test_contrasena_nueva_oculta_con_confirmacion(capsys):
    with patch.object(contrasena_service, "getpass",
                      side_effect=["corta", VALIDA, "Otra#Cosa1", VALIDA, VALIDA]) as oculta, \
         patch("builtins.input", side_effect=AssertionError("la contraseña no se pide con input")):
        assert contrasena_service.pedir_contrasena_nueva("ana@x.example", "Ana", "Gómez") == VALIDA
    salida = capsys.readouterr().out
    assert "al menos 8 caracteres" in salida and "no coinciden" in salida
    assert oculta.call_count == 5 and VALIDA not in salida


def test_contrasena_nueva_se_cancela_con_enter():
    with patch.object(contrasena_service, "getpass", return_value=""):
        assert contrasena_service.pedir_contrasena_nueva("a@x.example", "Ana", "Bo") is None


def test_alta_de_usuario_guarda_solo_el_hash():
    with patch.object(usuario_service, "seleccionar_parte", return_value=(None, None, None)), \
         patch.object(usuario_service, "seleccionar_rol", return_value=2), \
         patch.object(usuario_service, "seleccionar_estado", return_value="ACTIVO"), \
         patch.object(usuario_service, "email_en_uso", return_value=False), \
         patch.object(contrasena_service, "getpass", side_effect=[VALIDA, VALIDA]), \
         patch.object(usuario_service, "crear_usuario", return_value=9) as crear, \
         patch("builtins.input", side_effect=["Ana", "Gómez", "ana@x.example", ""]):
        usuario_service.registrar_usuario()
    guardado = crear.call_args.args[0]
    assert guardado.contrasena_encriptada != VALIDA
    assert verificar_contrasena(VALIDA, guardado.contrasena_encriptada)


def test_modificar_usuario_no_pide_ni_toca_la_contrasena():
    fila = (9, None, 2, "Ana", "Gómez", "ana@x.example", "ACTIVO", None, None, None, None, None, 0, False)
    with patch.object(usuario_service, "buscar_usuario_por_id", return_value=fila), \
         patch.object(usuario_service, "seleccionar_parte", return_value=(None, None, None)), \
         patch.object(usuario_service, "seleccionar_rol", return_value=2), \
         patch.object(usuario_service, "seleccionar_estado", return_value="ACTIVO"), \
         patch.object(usuario_service, "email_en_uso", return_value=False), \
         patch.object(usuario_service, "modificar_usuario", return_value=True) as modificar, \
         patch.object(contrasena_service, "getpass", side_effect=AssertionError("no pide contraseña")), \
         patch("builtins.input", side_effect=["9", "Ana", "Gómez", "ana@x.example", ""]):
        usuario_service.modificar_usuario_service()
    from app.repositories import usuario_repository
    cursor = MagicMock()
    cursor.rowcount = 1
    with patch.object(usuario_repository, "get_postgres_connection", return_value=conexion_mock(cursor)):
        usuario_repository.modificar_usuario(9, modificar.call_args.args[1])
    assert "contrasena" not in cursor.execute.call_args.args[0]


def test_email_repetido_sin_distinguir_mayusculas(capsys):
    with patch.object(usuario_service, "email_en_uso", side_effect=[True, False]), \
         patch("builtins.input", side_effect=["Ana@X.example", "otra@x.example"]):
        assert usuario_service.pedir_email_libre() == "otra@x.example"
    assert "ya existe un usuario con ese email" in capsys.readouterr().out


# ------------------------------------------------------------ 3. cambio y restablecimiento

def _datos():
    return (generar_hash_contrasena(CLAVE_TEST), "ana@empresa.example", "Ana", "Gómez")


def test_cambiar_mi_contrasena_pide_la_actual(capsys):
    with patch.object(autenticacion, "obtener_sesion_actual", return_value=sesion(nivel=2)), \
         patch.object(contrasena_service, "obtener_sesion_actual", return_value=sesion(nivel=2)), \
         patch.object(contrasena_service.usuario_repository, "datos_para_contrasena", return_value=_datos()), \
         patch.object(contrasena_service.sesion_repository, "registrar_intento_fallido",
                      return_value=(1, False)) as fallido, \
         patch.object(contrasena_service.usuario_repository, "actualizar_contrasena") as actualizar, \
         patch.object(contrasena_service, "getpass", return_value="Incorrecta#1"), \
         patch("builtins.input", return_value=""):
        contrasena_service.cambiar_mi_contrasena_service()
    assert "no es correcta" in capsys.readouterr().out
    fallido.assert_called_once_with(4)
    actualizar.assert_not_called()


def test_cambiar_mi_contrasena_guarda_y_cierra_las_otras_sesiones():
    with patch.object(autenticacion, "obtener_sesion_actual", return_value=sesion(nivel=2)), \
         patch.object(contrasena_service, "obtener_sesion_actual", return_value=sesion(nivel=2)), \
         patch.object(contrasena_service.usuario_repository, "datos_para_contrasena", return_value=_datos()), \
         patch.object(contrasena_service.usuario_repository, "actualizar_contrasena") as actualizar, \
         patch.object(contrasena_service.sesion_repository, "cerrar_sesiones_de_usuario") as cerrar, \
         patch.object(contrasena_service, "getpass", side_effect=[CLAVE_TEST, CLAVE_TEST, VALIDA, VALIDA]), \
         patch("builtins.input", return_value=""):
        contrasena_service.cambiar_mi_contrasena_service()
    id_usuario, nuevo_hash, debe_cambiar = actualizar.call_args.args
    assert id_usuario == 4 and debe_cambiar is False and verificar_contrasena(VALIDA, nuevo_hash)
    cerrar.assert_called_once_with(4, 4, 30)       # conserva la sesión actual


def test_la_nueva_debe_ser_distinta_de_la_actual(capsys):
    with patch.object(contrasena_service, "getpass", side_effect=[CLAVE_TEST, ""]):
        assert contrasena_service.pedir_contrasena_nueva(
            "ana@x.example", "Ana", "Gómez", generar_hash_contrasena(CLAVE_TEST)) is None
    assert "distinta de la actual" in capsys.readouterr().out


def test_restablecer_exige_administrador_y_obliga_a_cambiarla():
    usuario = (8, None, 2, "Sofía", "Lagos", "sofia@x.example", "ACTIVO", None, 2, None, "Seguros", None, 0, False)
    with patch.object(contrasena_service, "obtener_sesion_actual", return_value=sesion()), \
         patch("app.services.usuario_service.pedir_id", return_value=8), \
         patch.object(contrasena_service.usuario_repository, "buscar_usuario_por_id", return_value=usuario), \
         patch.object(contrasena_service.usuario_repository, "actualizar_contrasena") as actualizar, \
         patch.object(contrasena_service.sesion_repository, "cerrar_sesiones_de_usuario") as cerrar, \
         patch.object(contrasena_service, "getpass", side_effect=[VALIDA, VALIDA]), \
         patch("builtins.input", return_value=""):
        contrasena_service.restablecer_contrasena_service()
    assert actualizar.call_args.args[0] == 8 and actualizar.call_args.args[2] is True
    cerrar.assert_called_once_with(8, 4, None)     # todas sus sesiones


def test_restablecer_bloqueado_para_nivel_bajo_o_externos(capsys):
    for s in (sesion(nivel=2), sesion(nivel=5, id_cliente=6)):
        with patch.object(autenticacion, "obtener_sesion_actual", return_value=s), \
             patch("builtins.input", side_effect=AssertionError("no debe pedir datos")):
            assert contrasena_service.restablecer_contrasena_service() is None
            assert contrasena_service.desbloquear_usuario_service() is None


def test_desbloquear_no_cambia_la_contrasena(capsys):
    usuario = (6, None, 2, "Diego", "Ferreyra", "d@x.example", "ACTIVO", None, None, 1, "Andinos", None, 5, False)
    with patch.object(contrasena_service, "obtener_sesion_actual", return_value=sesion()), \
         patch.object(contrasena_service.sesion_repository, "listar_usuarios_bloqueados", return_value=[]), \
         patch("app.services.usuario_service.pedir_id", return_value=6), \
         patch.object(contrasena_service.usuario_repository, "buscar_usuario_por_id", return_value=usuario), \
         patch.object(contrasena_service.usuario_repository, "desbloquear_usuario", return_value=True) as desbloquear, \
         patch.object(contrasena_service.usuario_repository, "actualizar_contrasena") as actualizar, \
         patch("builtins.input", side_effect=["S", ""]):
        contrasena_service.desbloquear_usuario_service()
    desbloquear.assert_called_once_with(6)
    actualizar.assert_not_called()
    assert "La contraseña no cambió" in capsys.readouterr().out


def test_no_se_restablece_ni_desbloquea_la_propia_cuenta(capsys):
    with patch.object(contrasena_service, "obtener_sesion_actual", return_value=sesion()), \
         patch("app.services.usuario_service.pedir_id", return_value=4), \
         patch.object(contrasena_service.usuario_repository, "actualizar_contrasena") as actualizar, \
         patch("builtins.input", return_value=""):
        contrasena_service.restablecer_contrasena_service()
    actualizar.assert_not_called()
    assert "Cambiar mi contraseña" in capsys.readouterr().out


# ------------------------------------------------------------ 4. bloqueo e inicio de sesión

def fila_login(hash_, estado="ACTIVO", bloqueado=False, minutos=15, debe_cambiar=False):
    return (6, "Diego", "Ferreyra", "diego@x.example", hash_, estado, "Usuario", 2,
            bloqueado, minutos, debe_cambiar)


def _login(fila, clave, **parches):
    objetivos = {
        "buscar_usuario_por_email": dict(return_value=fila),
        "registrar_intento_fallido": dict(return_value=(1, False)),
        "registrar_ingreso_correcto": {},
        "iniciar_sesion_db": dict(return_value=70),
        "establecer_sesion": {},
        "cerrar_sesion_db": {},
        "limpiar_sesion": {},
    }
    for nombre, valor in parches.items():
        objetivos[nombre] = valor
    pila = [patch.object(sesion_service, n, **kw) for n, kw in objetivos.items()]
    pila += [patch.object(sesion_service, "obtener_sesion_actual", return_value=None),
             patch.object(sesion_service, "getpass", return_value=clave),
             patch("builtins.input", return_value="diego@x.example")]
    mocks = {}
    for p, n in zip(pila, list(objetivos) + ["_", "_g", "_i"]):
        mocks[n] = p.start()
    try:
        resultado = sesion_service.iniciar_sesion_service()
    finally:
        for p in pila:
            p.stop()
    return resultado, mocks


def test_contrasena_incorrecta_suma_un_intento(capsys):
    ok, m = _login(fila_login(generar_hash_contrasena(CLAVE_TEST)), "Mala#Clave1")
    assert ok is False
    m["registrar_intento_fallido"].assert_called_once_with(6)
    m["iniciar_sesion_db"].assert_not_called()
    assert "Email o contraseña incorrectos" in capsys.readouterr().out


def test_el_quinto_intento_bloquea_15_minutos(capsys):
    ok, _ = _login(fila_login(generar_hash_contrasena(CLAVE_TEST)), "Mala#Clave1",
                   registrar_intento_fallido=dict(return_value=(5, True)))
    assert ok is False
    assert "bloqueado por 15 minutos" in capsys.readouterr().out
    assert politica.INTENTOS_MAXIMOS == 5 and politica.MINUTOS_BLOQUEO == 15


def test_usuario_bloqueado_no_entra_ni_con_la_clave_correcta(capsys):
    ok, m = _login(fila_login(generar_hash_contrasena(CLAVE_TEST), bloqueado=True, minutos=9), CLAVE_TEST)
    assert ok is False
    m["iniciar_sesion_db"].assert_not_called()
    m["registrar_intento_fallido"].assert_not_called()
    assert "Probá de nuevo en 9 minutos" in capsys.readouterr().out


def test_ingreso_correcto_reinicia_intentos_e_inicia_sesion():
    ok, m = _login(fila_login(generar_hash_contrasena(CLAVE_TEST)), CLAVE_TEST)
    assert ok is True
    m["registrar_ingreso_correcto"].assert_called_once_with(6)
    m["establecer_sesion"].assert_called_once_with(70, 6)


def test_inactivo_solo_se_informa_con_la_clave_correcta(capsys):
    _login(fila_login(generar_hash_contrasena(CLAVE_TEST), estado="INACTIVO"), "Mala#Clave1")
    assert "inactivo" not in capsys.readouterr().out
    ok, m = _login(fila_login(generar_hash_contrasena(CLAVE_TEST), estado="INACTIVO"), CLAVE_TEST)
    assert ok is False and "inactivo" in capsys.readouterr().out
    m["iniciar_sesion_db"].assert_not_called()


def test_despues_de_un_reseteo_hay_que_cambiarla_al_entrar():
    with patch("app.services.contrasena_service.cambio_obligatorio", return_value=False) as cambio:
        ok, m = _login(fila_login(generar_hash_contrasena(CLAVE_TEST), debe_cambiar=True), CLAVE_TEST)
    cambio.assert_called_once()
    assert ok is False
    m["cerrar_sesion_db"].assert_called_once_with(70, 6)


def test_el_log_nunca_guarda_la_contrasena_ni_lo_tipeado(caplog):
    with caplog.at_level(logging.INFO, logger="logistica"):
        _login(fila_login(generar_hash_contrasena(CLAVE_TEST)), "Secreta#Mal9",
               registrar_intento_fallido=dict(return_value=(5, True)))
        _login(None, "Secreta#Mal9")
        _login(fila_login(generar_hash_contrasena(CLAVE_TEST)), CLAVE_TEST)
    texto = caplog.text
    assert "Secreta#Mal9" not in texto and CLAVE_TEST not in texto and "pbkdf2" not in texto
    assert "diego@x.example" not in texto
    assert "usuario 6 (intento 5 de 5)" in texto and "bloqueado por 15 minutos" in texto
    assert "email no registrado" in texto


def test_bloqueo_en_una_sola_sentencia_con_los_parametros():
    from app.repositories import sesion_repository as repo
    cursor = MagicMock()
    cursor.fetchone.return_value = (5, True)
    with patch.object(repo, "get_postgres_connection", return_value=conexion_mock(cursor)):
        assert repo.registrar_intento_fallido(6) == (5, True)
    sql, params = cursor.execute.call_args.args
    assert sql.strip().startswith("UPDATE usuario") and params == (5, 15, 6)


# ------------------------------------------------------------ 5. inactividad

def _sesion_db(expirada, registrar):
    return (30, 4, "Ana", "Gómez", "ana@x.example", "Administrador", 5, None, None, None,
            expirada, registrar)


@pytest.mark.sesion_real
def test_sesion_inactiva_30_minutos_se_cierra_con_aviso():
    cursor = MagicMock()
    cursor.fetchone.return_value = _sesion_db(True, True)
    autenticacion.establecer_sesion(30, 4)
    with patch.object(autenticacion, "get_postgres_connection", return_value=conexion_mock(cursor)):
        assert autenticacion.obtener_sesion_actual() is None
    sentencias = [c.args[0] for c in cursor.execute.call_args_list]
    assert "EXPIRADA" in sentencias[1]
    assert cursor.execute.call_args_list[0].args[1][:2] == (30, 60)
    assert autenticacion.tomar_aviso_cierre() == "Tu sesión se cerró por inactividad (30 minutos)."


@pytest.mark.sesion_real
def test_la_actividad_se_registra_a_lo_sumo_una_vez_por_minuto():
    cursor = MagicMock()
    autenticacion.establecer_sesion(30, 4)
    try:
        for registrar, esperadas in ((False, 1), (True, 2)):
            cursor.reset_mock()
            cursor.fetchone.return_value = _sesion_db(False, registrar)
            with patch.object(autenticacion, "get_postgres_connection", return_value=conexion_mock(cursor)):
                assert autenticacion.obtener_sesion_actual()["id_usuario"] == 4
            assert cursor.execute.call_count == esperadas
        assert "ultima_actividad = now()" in cursor.execute.call_args.args[0]
    finally:
        autenticacion.limpiar_sesion()


def test_sesiones_activas_muestra_bloqueados_y_cierra_las_vencidas(capsys):
    from datetime import datetime, timezone
    bloqueado = [(6, "Diego", "Ferreyra", "d@x.example", datetime(2026, 11, 1, 18, 0, tzinfo=timezone.utc))]
    with patch.object(sesion_service, "verificar_permiso", return_value=True), \
         patch.object(sesion_service, "expirar_sesiones_inactivas", return_value=2), \
         patch.object(sesion_service, "listar_sesiones_activas", return_value=[]), \
         patch.object(sesion_service, "listar_usuarios_bloqueados", return_value=bloqueado), \
         patch("builtins.input", return_value=""):
        sesion_service.consultar_sesiones_activas_service()
    salida = capsys.readouterr().out
    assert "Diego Ferreyra" in salida and "bloqueado hasta 01/11/2026 15:00" in salida
    assert "Se cerraron 2 sesión(es) por inactividad" in salida


def test_listado_de_usuarios_muestra_el_bloqueo(capsys):
    from datetime import datetime, timezone
    fila = (6, None, 2, "Diego", "Ferreyra", "d@x.example", "ACTIVO", None, None, 1, "Andinos",
            datetime(2026, 11, 1, 18, 0, tzinfo=timezone.utc), 5, False)
    usuario_service.mostrar_usuario(fila)
    assert "Bloqueado hasta: 01/11/2026 15:00" in capsys.readouterr().out


# ------------------------------------------------------------ 6. validaciones de datos

@pytest.mark.parametrize("cuit, pais, esperado", [
    ("30-71234567-1", "Argentina", "30-71234567-1"),
    ("30712345671", "argentina", "30-71234567-1"),
    ("76.543.210-K", "Chile", "76.543.210-K"),
    ("217654320019", "Uruguay", "217654320019"),
    ("80034567-1", "Paraguay", "80034567-1"),
])
def test_identificacion_fiscal_por_pais(cuit, pais, esperado):
    assert v.validar_identificacion_fiscal(cuit, pais) == esperado


@pytest.mark.parametrize("cuit, pais, mensaje", [
    ("30-71234567-8", "Argentina", "dígito verificador"),
    ("3071234", "Argentina", "11 dígitos"),
    ("AB", "Chile", "6 a 13 caracteres"),
    ("ABCDEFGH", "Chile", "al menos 5 dígitos"),
])
def test_identificacion_fiscal_invalida(cuit, pais, mensaje):
    with pytest.raises(ValueError, match=mensaje):
        v.validar_identificacion_fiscal(cuit, pais)


def test_email_telefono_y_largos():
    assert v.validar_email("compras@vinedos.example") == "compras@vinedos.example"
    for malo in ("sin-arroba", "a@b", "a@b.c", "a..b@x.example", "a@-x.example"):
        with pytest.raises(ValueError):
            v.validar_email(malo)
    with pytest.raises(ValueError, match="150 caracteres"):
        v.validar_email("a" * 141 + "@x.example")
    assert v.validar_telefono("+56 2 2345 6789") == "+56 2 2345 6789"
    assert v.validar_telefono("") is None
    for malo in ("12345", "011-ABCD-123", "1" * 31):
        with pytest.raises(ValueError):
            v.validar_telefono(malo)
    with pytest.raises(ValueError, match="La razón social no puede superar 150"):
        v.validar_contacto({"razon_social": "x" * 151, "cuit": "30-71234567-1", "pais": "Argentina",
                            "email": "a@x.example"}, cuit_por_pais=True)


def test_importes_positivos_con_maximo_por_operacion():
    assert v.validar_importe("1.500,5".replace(".", "")) == Decimal("1500.50")
    assert v.validar_importe("100000000") == Decimal("100000000.00")
    for malo, mensaje in (("0", "mayor a cero"), ("-5", "mayor a cero"), ("1.234", "2 decimales"),
                          ("100000000.01", r"\$100\.000\.000,00"), ("abc", "no es un importe")):
        with pytest.raises(ValueError, match=mensaje):
            v.validar_importe(malo)
    assert v.validar_importe("0", permitir_cero=True) == Decimal("0.00")


def test_maximo_en_pagos_facturas_recibidas_y_precios():
    from app.repositories import facturacion_repository, precios_repository
    from app.utils.validaciones_terceros import importe_positivo
    with pytest.raises(ValueError, match="100.000.000"):
        importe_positivo("150000000", "x")
    with pytest.raises(ValueError, match="100.000.000"):
        facturacion_repository._importe_positivo("100000000.50", "x")
    with pytest.raises(ValueError, match="100.000.000"):
        precios_repository.validar_precios("0", {"Terrestre": "1", "Marítimo": "1", "Aéreo": "200000000"})


def test_fechas_coherentes_y_cantidades_maximas():
    from datetime import date
    with pytest.raises(ValueError, match="no puede ser posterior"):
        v.validar_rango(date(2026, 11, 2), date(2026, 11, 1))
    from app.utils.validaciones_contenedor import validar_capacidad
    with pytest.raises(ValueError, match="100 toneladas"):
        validar_capacidad("100,5")
    from app.services import tarifas_service
    with patch.object(tarifas_service.repo, "agregar_carga") as agregar:
        with pytest.raises(ValueError, match="100000 kg"):
            tarifas_service.registrar_partida_carga(18, "VINO", "100001", False)
        agregar.assert_not_called()
    with pytest.raises(ValueError, match="40000 km"):
        tarifas_service.registrar_distancia_tramo(1, "40001")


def test_reportes_vuelven_a_pedir_si_desde_es_posterior(capsys):
    from app.services import reportes_pantallas
    with patch("builtins.input", side_effect=["2026-10-31", "2026-10-01", "2026-10-01", "2026-10-31"]):
        desde, hasta = reportes_pantallas.pedir_periodo()
    assert (str(desde), str(hasta)) == ("2026-10-01", "2026-10-31")
    assert "no puede ser posterior" in capsys.readouterr().out


def test_alta_de_cliente_valida_antes_de_escribir():
    from app.models.cliente import Cliente
    from app.repositories import cliente_repository
    with patch.object(cliente_repository, "get_postgres_connection") as conexion:
        with pytest.raises(ValueError, match="dígito verificador"):
            cliente_repository.crear_cliente(Cliente(
                "Distribuidora", "30-71234567-8", "a@x.example", None, "Calle 1", "Argentina", "ACTIVO"))
        with pytest.raises(ValueError, match="identificación fiscal"):
            cliente_repository.crear_cliente(Cliente(
                "Viñedos", "K", "a@x.example", None, "Calle 1", "Chile", "ACTIVO"))
    conexion.assert_not_called()


def test_alta_de_usuario_y_tercero_validan_antes_de_escribir():
    from app.models.usuario import Usuario
    from app.repositories import terceros_repository, usuario_repository
    with patch.object(usuario_repository, "get_postgres_connection") as conexion:
        with pytest.raises(ValueError, match="80 caracteres"):
            usuario_repository.crear_usuario(Usuario(None, 2, "x" * 81, "Bo", "a@x.example", "h", "ACTIVO"))
    conexion.assert_not_called()
    with patch.object(terceros_repository, "get_postgres_connection") as conexion:
        with pytest.raises(ValueError, match="email ingresado no es válido"):
            terceros_repository.crear_proveedor({
                "razon_social": "Seguros", "cuit": "30-71234567-1", "email": "mal", "pais": "Argentina",
                "rubro": "SEGUROS"})
    conexion.assert_not_called()


# ------------------------------------------------------------ 7. permisos en el servicio

def test_cada_servicio_de_los_menus_internos_verifica_su_permiso():
    from app.utils.permisos_menus import servicios_por_menu
    servicios = servicios_por_menu()
    assert len(servicios) >= 100
    faltan = []
    for (modulo, nombre), nivel in servicios.items():
        funcion = getattr(importlib.import_module(modulo), nombre)
        if getattr(funcion, "nivel_requerido", None) != nivel:
            faltan.append(f"{modulo}.{nombre} (menú {nivel}, servicio "
                          f"{getattr(funcion, 'nivel_requerido', 'sin control')})")
    assert not faltan, faltan


def test_el_servicio_rechaza_externos_y_niveles_bajos(capsys):
    from app.services import facturacion_service, terceros_service, envio_service
    casos = [(facturacion_service.registrar_pago_service, sesion(nivel=2)),
             (terceros_service.registrar_tercero_service, sesion(nivel=2)),
             (envio_service.registrar_envio, sesion(nivel=5, id_operador=1)),
             (usuario_service.eliminar_usuario_service, sesion(nivel=3))]
    for funcion, s in casos:
        with patch.object(autenticacion, "obtener_sesion_actual", return_value=s), \
             patch("builtins.input", side_effect=AssertionError("no debe pedir datos")):
            assert funcion() is None, funcion.__name__


def test_logica_de_tarifas_lanza_permission_error():
    from app.services import tarifas_service
    with patch.object(autenticacion, "obtener_sesion_actual", return_value=sesion(nivel=2)):
        with pytest.raises(PermissionError):
            tarifas_service.registrar_tipo_carga("VINO", "Vino")


def test_el_portal_solo_entra_con_su_dato_ya_verificado(capsys):
    from app.services import trazabilidad_service as t
    cliente = sesion(nivel=2, id_cliente=6)
    with patch.object(autenticacion, "obtener_sesion_actual", return_value=cliente), \
         patch("builtins.input", side_effect=AssertionError("no debe pedir un envío cualquiera")):
        assert t.historial_envio_service() is None
    assert "no disponible para tu usuario" in capsys.readouterr().out
    with patch.object(autenticacion, "obtener_sesion_actual", return_value=cliente), \
         patch.object(t, "listar_eventos_envio", return_value=[]), patch("builtins.input", return_value=""):
        t.historial_envio_service((18, 6, None, "Mendoza", "Santiago", "En tránsito"))
    assert "Envío 18" in capsys.readouterr().out


def test_el_cliente_usa_mis_reportes_y_no_los_submenus_internos(capsys):
    from app.services import reportes_pantallas as pantallas
    cliente = sesion(nivel=2, id_cliente=6)
    with patch.object(autenticacion, "obtener_sesion_actual", return_value=cliente), \
         patch.object(pantallas, "obtener_sesion_actual", return_value=cliente), \
         patch.object(pantallas.repo, "listar_reportes", return_value=[]) as listar, \
         patch("builtins.input", side_effect=["1", "", "0"]):
        pantallas.mis_reportes_menu()
    listar.assert_called_once_with(6)
    assert "no disponible" not in capsys.readouterr().out
    with patch.object(autenticacion, "obtener_sesion_actual", return_value=cliente), \
         patch("builtins.input", side_effect=AssertionError("no debe mostrar el submenú")):
        assert pantallas.submenu("REPORTES COBRABLES", pantallas.REPORTES_COBRABLES) is None


# ------------------------------------------------------------ 7. SQL parametrizado

# Lo único que se interpola en SQL: nombres de tablas/columnas elegidos de
# listas fijas del código y fragmentos constantes. Los valores van siempre
# como parámetros (%s). Una interpolación nueva hace fallar este test para
# revisarla.
INTERPOLACIONES_PERMITIDAS = {
    "columna", "tabla", "expresion", "filtro", "_COLUMNAS", "COLUMNAS_OPERADOR",
    "c['tabla']", "c['id']", "c['columnas']", "c['extra']", "_dia('e.fecha_creacion')",
    "_dia('e.fecha_entrega')", "_dia('i.fecha')", "_dia('COALESCE(e.fecha_entrega, now())')",
    "_dia('fecha_creacion')", "'FOR UPDATE' if bloquear else ''", "_MERGE_OPERADOR",
    "_SELECT_VEHICULO", "_SELECT_USUARIO", "'FOR SHARE' if bloquear else ''",
}


def _interpolaciones(nodo):
    if isinstance(nodo, ast.JoinedStr):
        return [ast.unparse(x.value) for x in nodo.values if isinstance(x, ast.FormattedValue)]
    if isinstance(nodo, ast.BinOp) and isinstance(nodo.op, ast.Add):
        return _interpolaciones(nodo.left) + _interpolaciones(nodo.right)
    if isinstance(nodo, ast.Name):
        return [nodo.id] if nodo.id.isupper() or nodo.id.startswith("_") else []
    if isinstance(nodo, ast.Constant):
        return []
    if isinstance(nodo, ast.Call) and getattr(nodo.func, "attr", "") == "format":
        return ["<.format()>"]
    if isinstance(nodo, ast.BinOp) and isinstance(nodo.op, ast.Mod):
        return ["<% formato>"]
    return []


def test_ninguna_consulta_arma_sql_con_valores():
    raiz = Path(__file__).resolve().parents[1] / "app"
    problemas = []
    for archivo in raiz.rglob("*.py"):
        arbol = ast.parse(archivo.read_text(encoding="utf-8"))
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Call) and getattr(nodo.func, "attr", "") in ("execute", "_q") \
                    or isinstance(nodo, ast.Call) and getattr(nodo.func, "id", "") == "_q":
                if not nodo.args:
                    continue
                for expresion in _interpolaciones(nodo.args[0]):
                    if expresion not in INTERPOLACIONES_PERMITIDAS:
                        problemas.append(f"{archivo.name}:{nodo.lineno}: {expresion}")
    assert not problemas, problemas


def test_los_nombres_interpolados_salen_de_listas_fijas():
    from app.repositories import cuenta_tercero_repository, terceros_repository
    assert set(cuenta_tercero_repository._TITULARES.values()) == {
        ("proveedor", "id_proveedor"), ("operador_logistico", "id_operador")}
    with pytest.raises(ValueError):
        terceros_repository._config("usuario; DROP TABLE usuario")


# ------------------------------------------------------------ sin datos sensibles

def test_ningun_mensaje_ni_modelo_muestra_el_hash():
    from app.models.usuario import Usuario
    texto = str(Usuario(None, 2, "Ana", "Gómez", "a@x.example", "pbkdf2_sha256$1$aa$bb", "ACTIVO"))
    assert "pbkdf2" not in texto and "contrase" not in texto.lower()
    fuente = inspect.getsource(contrasena_service) + inspect.getsource(sesion_service)
    for nombre in ("contrasena", "nueva", "actual"):
        assert f"logger.info(\"%s\", {nombre})" not in fuente
    # Ningún logger recibe la variable con la contraseña.
    arbol = ast.parse(fuente)
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Attribute) \
                and getattr(nodo.func.value, "id", "") == "logger":
            nombres = {n.id for n in ast.walk(nodo) if isinstance(n, ast.Name)}
            assert not nombres & {"contrasena", "nueva", "actual", "hash_actual", "hash_guardado"}, \
                ast.unparse(nodo)
