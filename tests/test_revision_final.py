"""Revisión final: formato argentino, mensajes de error claros y textos."""

from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import psycopg.errors as pe
import pytest

from app.utils import formato
from app.utils.errores import mensaje_error


# ------------------------------------------------------------ formato

def test_importes_y_numeros_en_formato_argentino():
    assert formato.dinero(Decimal("1107150.00")) == "$1.107.150,00"
    assert formato.dinero(Decimal("-47500")) == "-$47.500,00"
    assert formato.numero(66.666, 1) == "66,7"
    assert formato.porcentaje(44.44) == "44,4 %"
    assert formato.entero(Decimal("240800")) == "240.800"
    assert formato.compacto(Decimal("20.00")) == "20"
    assert formato.compacto(4.18) == "4,18"
    assert formato.compacto(-32.597321, 5) == "-32,59732"


def test_fechas_dd_mm_aaaa_en_hora_argentina():
    utc = datetime(2026, 10, 27, 11, 42, 32, 373000, tzinfo=timezone.utc)
    assert formato.fecha_hora(utc) == "27/10/2026 08:42"
    assert formato.fecha(utc) == "27/10/2026"
    assert formato.fecha(date(2026, 10, 1)) == "01/10/2026"
    assert formato.fecha_hora("2026-09-11T20:00:00-03:00") == "11/09/2026 20:00"
    assert formato.fecha(None) == "-"
    assert formato.mes("2026-10") == "10/2026"


def test_codigos_internos_con_nombre_para_mostrar():
    assert formato.evento("CARGA_INICIADA") == "Carga iniciada"
    assert formato.evento("EN_TRANSITO") == "En tránsito"
    assert formato.descripcion_movimiento("FACTURA", "13", "envio=13;regla=1;envio_manual") == \
        "Factura N.º 13 del envío 13"
    assert formato.descripcion_movimiento("FACTURA", "8", "envio=10;regla=1;envio_automatica") == \
        "Factura N.º 8 del envío 10 (automática)"
    assert formato.descripcion_movimiento("FACTURA", "4", "factura_manual") == "Factura N.º 4 (histórica)"
    assert formato.descripcion_movimiento("PAGO", "10", "factura=8;metodo=Transferencia") == \
        "Pago N.º 10 de la factura N.º 8 (transferencia)"
    assert formato.descripcion_movimiento("FACTURA_RECIBIDA", "14", "proveedor=2;comprobante=A-0010-00000777") == \
        "Factura recibida A-0010-00000777"
    assert formato.descripcion_movimiento("PAGO_EMITIDO", "9", "factura_recibida=14;metodo=Transferencia") == \
        "Pago emitido (transferencia)"


def test_texto_de_reportes_usa_formato_argentino():
    from app.utils.exportar_reportes import texto
    assert texto(Decimal("1107150.00")) == "1.107.150,00"
    assert texto(Decimal("3")) == "3"
    assert texto(48.9) == "48,9"
    assert texto(True) == "Sí"


# ------------------------------------------------------------ errores

def _error(clase, texto, tabla=None):
    error = clase(texto)
    if tabla is not None:
        diag = MagicMock(table_name=tabla)
        with patch.object(clase, "diag", new=diag, create=True):
            return mensaje_error(error)
    return mensaje_error(error)


def test_eliminar_con_datos_asociados_da_un_mensaje_claro():
    texto = ('update o delete en «cliente» viola la llave foránea «fk_apertura_cliente» '
             'en la tabla «apertura_cuenta_corriente»')
    mensaje = _error(pe.ForeignKeyViolation, texto, "apertura_cuenta_corriente")
    assert mensaje.startswith("No se puede eliminar porque tiene una cuenta corriente abierta")
    assert "fk_" not in mensaje and "«" not in mensaje


def test_otros_errores_de_la_base_sin_detalle_tecnico():
    assert mensaje_error(pe.UniqueViolation("llave duplicada viola uq_x")) == "Ya existe un registro con esos datos."
    assert "conectar" in mensaje_error(pe.OperationalError("connection refused"))
    generico = mensaje_error(KeyError("x"))
    assert generico.startswith("Ocurrió un error inesperado") and "KeyError" not in generico
    assert "list index" not in mensaje_error(IndexError("list index out of range"))


def test_errores_de_validacion_se_muestran_tal_cual():
    assert mensaje_error(ValueError("El CUIT es obligatorio.")) == "El CUIT es obligatorio."
    assert mensaje_error(PermissionError("Opción solo para internos.")) == "Opción solo para internos."


def test_errores_tecnicos_de_python_no_se_muestran_y_van_al_log(caplog):
    from app.utils.errores import GENERICO
    for error in (ValueError("invalid literal for int() with base 10: 'x'"),
                  ValueError("Invalid isoformat string: '2026-13-01'"),
                  UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte"),
                  RecursionError("maximum recursion depth exceeded"),
                  RuntimeError("dictionary changed size during iteration"),
                  ValueError("None")):
        with caplog.at_level("ERROR", logger="logistica.errores"):
            caplog.clear()
            assert mensaje_error(error) == GENERICO
        assert caplog.records, f"no quedó en el log: {error!r}"
    archivo = PermissionError(13, "Permission denied", r"C:\Users\x\reportes\1.pdf")
    texto = mensaje_error(archivo)
    assert texto == "No se pudo acceder al archivo o a la carpeta indicada." and "Users" not in texto


def test_errores_propios_de_la_aplicacion_se_muestran_tal_cual():
    from app.repositories.facturacion_repository import FacturaExistente
    from app.services.cierre_cuenta_service import CierreBloqueado
    assert mensaje_error(FacturaExistente("El envío ya tiene la factura 13.")) == "El envío ya tiene la factura 13."
    assert mensaje_error(CierreBloqueado("La moneda de la cuenta no está configurada explícitamente.")) == \
        "La moneda de la cuenta no está configurada explícitamente."
    assert mensaje_error(RuntimeError("El envío no está en el grafo.")) == "El envío no está en el grafo."


def test_listas_de_errores_guardan_el_texto_traducido():
    from app.services import sincronizacion_service as s
    from app.utils.errores import GENERICO
    with patch.object(s, "listar_ids_envios", return_value=[7]), \
         patch.object(s, "reconciliar_envio", side_effect=TypeError("'NoneType' object is not subscriptable")), \
         patch.object(s, "_marcar_pendiente"):
        _, errores = s.resincronizar_todos()
    assert errores == [(7, GENERICO)]
    from app.services import reportes_cobrables_service as cobrables
    import psycopg.errors as pe2
    with patch.object(cobrables.repo, "listar_reportes", return_value=[{"id_reporte": 1}]), \
         patch.object(cobrables, "emitir_factura_reporte",
                      side_effect=pe2.UniqueViolation("llave duplicada viola uq_factura_reporte")):
        _, errores = cobrables.facturar_pendientes()
    assert errores == [(1, "Ya existe un registro con esos datos.")]


def test_servicios_no_disponibles():
    from pymongo.errors import ServerSelectionTimeoutError
    assert "eventos, alertas y mensajes" in mensaje_error(ServerSelectionTimeoutError("localhost:27017"))


# ------------------------------------------------------------ textos

def test_obligatorio_concuerda_con_el_articulo():
    from app.utils.validaciones import es_obligatorio
    assert es_obligatorio("La razón social") == "La razón social es obligatoria."
    assert es_obligatorio("El CUIT") == "El CUIT es obligatorio."
    from app.utils.validaciones_logistica import validar_texto
    with pytest.raises(ValueError, match="La ubicación es obligatoria."):
        validar_texto("  ", "La ubicación")


def test_partida_de_carga_con_categoria_inexistente_vuelve_a_pedir(capsys):
    from app.ui import menu_tarifas
    with patch.object(menu_tarifas.repo, "listar_tipos_carga", return_value=[("VINO", "Vino")]), \
         patch.object(menu_tarifas.repo, "listar_envios_tarifables",
                      return_value=[(18, "x", "Mendoza", "Santiago", "En tránsito")]), \
         patch.object(menu_tarifas.service, "registrar_partida_carga") as registrar, \
         patch("builtins.input", side_effect=["99999", "18", "99999", "1", "100", "N", ""]):
        menu_tarifas._registrar_carga()
    salida = capsys.readouterr().out
    assert "Elegí uno de los envíos de la lista." in salida
    assert "Elegí un número entre 1 y 1." in salida
    registrar.assert_called_once()


def test_quien_llevo_el_contenedor_pide_el_codigo():
    from app.services import trazabilidad_service as t
    with patch.object(t, "cliente_visible", return_value=6), \
         patch("app.repositories.contenedor_repository.buscar_contenedor_por_codigo", return_value=None), \
         patch.object(t, "operadores_de_contenedor") as operadores, \
         patch("builtins.input", side_effect=["XXXX9999999", ""]), \
         patch.object(t, "obtener_sesion_actual", return_value={"id_cliente": 6}):
        t.quien_llevo_contenedor_service()
    operadores.assert_not_called()


def test_quien_llevo_en_el_portal_no_menciona_opciones_internas(capsys):
    from app.services import trazabilidad_service as t
    with patch.object(t, "cliente_visible", return_value=6), \
         patch("app.repositories.contenedor_repository.buscar_contenedor_por_codigo",
               return_value=(14, "TDSU1000103")), \
         patch.object(t, "operadores_de_contenedor", return_value=[]), \
         patch("builtins.input", side_effect=["TDSU1000103", ""]), \
         patch.object(t, "obtener_sesion_actual", return_value={"id_cliente": 6}):
        t.quien_llevo_contenedor_service()
    salida = capsys.readouterr().out
    assert "no tiene tramos en tus envíos" in salida and "opción 6" not in salida


def test_formato_del_reporte_se_valida_antes_de_confirmar(capsys):
    from app.services import reportes_pantallas as pantallas
    tipos = [("PUNTUALIDAD", "Puntualidad de mis envíos", "x", "x", Decimal("12000.00"), True)]
    with patch.object(pantallas.repo, "listar_tipos_reporte", return_value=tipos), \
         patch("builtins.input", side_effect=["1", "", "", "", "XLS", "PDF", "S"]):
        tipo, formato_archivo, _ = pantallas.pedir_solicitud()
    salida = capsys.readouterr().out
    assert formato_archivo == "PDF" and "Elegí CSV o PDF." in salida
    assert "$12.000,00" in salida


# ------------------------------------------------------------ presentación final

def test_mensaje_de_alerta_sin_titulo_repetido():
    from app.services.alertas_service import textos_mensaje
    interno, cliente = textos_mensaje(
        {"tipo": "Temperatura alta", "descripcion": "Temperatura alta: valor 10, límite 8",
         "severidad": "Alta", "envio_id": 18, "sensor_id": 41}, "TDSU1000130")
    assert cliente == "Alerta Alta en envío 18, contenedor TDSU1000130: Temperatura alta: valor 10, límite 8"
    assert interno.endswith("(sensor 41)")
    otro, _ = textos_mensaje({"tipo": "Falla de sensor", "descripcion": "Lecturas idénticas"}, None)
    assert otro == "Alerta: Falla de sensor. Lecturas idénticas"


def test_simular_lecturas_muestra_valores_y_no_el_id_de_lectura():
    from app.services.monitoreo_avanzado_service import describir_valores
    assert describir_valores({"temperatura": 6.25, "bateria": 80.12}) == "6,25 °C | batería 80,1 %"
    assert describir_valores({"gps_latitud": -34.512345, "gps_longitud": -58.4, "bateria": None}) == \
        "latitud -34,51235 | longitud -58,4"


def test_umbrales_sin_doble_espacio_y_con_coma():
    from app.services.incidentes_service import _texto_umbrales
    lineas = _texto_umbrales({("vibracion", "MAX"): [(Decimal("15"), "Alta", 1)],
                              ("temperatura", "MAX"): [(Decimal("8.5"), "Alta", 2)]})
    assert "  Vibración mayor a 15 -> Alta" in lineas
    assert "  Temperatura mayor a 8,5 °C -> Alta" in lineas


def test_resincronizar_un_envio_informa_el_resultado():
    from app.services import sincronizacion_service as s
    with patch.object(s, "reconciliar_envio"), patch.object(s, "resolver_pendientes_envio"):
        assert s.resincronizar_envio(14) is None
    from neo4j.exceptions import ServiceUnavailable
    with patch.object(s, "reconciliar_envio", side_effect=ServiceUnavailable("x")), \
         patch.object(s, "_marcar_pendiente") as marcar:
        motivo = s.resincronizar_envio(14)
    marcar.assert_called_once()
    assert motivo == "El servicio de la red de rutas no está disponible en este momento."


def test_capacidad_del_contenedor_en_toneladas():
    from app.models.contenedor import Contenedor
    assert "Capacidad: 3 toneladas" in str(Contenedor("X", "Dry", Decimal("3.00"), "Disponible"))
    from app.services import reportes_service
    with patch.object(reportes_service.repo, "ranking_clientes_volumen", return_value=[("a", "b", 1, 1, 2, 3)]):
        tabla = reportes_service.reporte_ranking_volumen(date(2026, 1, 1), date(2026, 12, 31))
    assert "Capacidad (t)" in tabla.columnas
