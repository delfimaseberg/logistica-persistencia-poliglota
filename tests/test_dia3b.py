"""Día 3B: predicción con clima e historial (29), reporte predictivo (34),
mensajes por alerta (26), fallas de sensor, reglas de alerta (9), sesiones
(3), sensores al entregar, listar_cargas_envio y textos de pantalla."""

import ast
import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.repositories import alerta_climatica_repository as clima_repo
from app.repositories import regla_alerta_repository as reglas_repo
from app.services import alertas_service
from app.services import deteccion_sensores as det
from app.services import predicciones_service as pred
from app.services.deteccion_sensores import REGLAS_POR_DEFECTO


AHORA = datetime(2026, 10, 31, 15, 0, tzinfo=timezone.utc)


def conexion_mock(cursor):
    conexion = MagicMock()
    conexion.__enter__.return_value = conexion
    conexion.cursor.return_value.__enter__.return_value = cursor
    return conexion


def lectura(minutos_atras, temperatura=None, humedad=None, id_lectura=None, **extra):
    datos = dict(temperatura=temperatura, humedad=humedad, vibracion=None, bateria=80.0,
                 gps_latitud=None, gps_longitud=None)
    datos.update(extra)
    return SimpleNamespace(fecha_hora=AHORA - timedelta(minutes=minutos_atras),
                           id_lectura=id_lectura or f"L{minutos_atras}", **datos)


# ------------------------------------------------------------ fallas de sensor

def test_valor_imposible_se_detecta_y_no_se_evalua_como_carga():
    mala = lectura(0, temperatura=-99.0)
    assert det.valores_imposibles(mala) == [("temperatura", -99.0)]
    fallas = det.fallas_de_sensor([mala], REGLAS_POR_DEFECTO)
    assert [f[0] for f in fallas] == [det.FALLA_VALOR]
    assert "Temperatura = -99" in fallas[0][2]
    from app.services.incidentes_service import detectar_anomalias
    assert detectar_anomalias(mala, REGLAS_POR_DEFECTO) == []


@pytest.mark.parametrize("campo,valor", [
    ("humedad", 140.0), ("bateria", -5.0), ("gps_latitud", 120.0), ("temperatura", float("nan")),
])
def test_otros_valores_imposibles(campo, valor):
    assert det.valores_imposibles(lectura(0, **{campo: valor}))


def test_valores_posibles_no_son_falla():
    assert det.valores_imposibles(lectura(0, temperatura=-20.0, humedad=100.0)) == []


def test_lecturas_congeladas_segun_la_regla():
    serie = [lectura(5 * i, temperatura=5.5, humedad=60.0) for i in range(6)]
    assert det.lecturas_congeladas(serie, 6) is True
    fallas = det.fallas_de_sensor(serie, REGLAS_POR_DEFECTO)
    assert [f[0] for f in fallas] == [det.FALLA_CONGELADA]
    # La clave de la alerta es la lectura más vieja de la serie congelada.
    assert fallas[0][3] == serie[5].id_lectura


def test_cinco_iguales_no_alcanzan_y_un_cambio_corta_la_serie():
    serie = [lectura(5 * i, temperatura=5.5) for i in range(5)]
    assert det.lecturas_congeladas(serie, 6) is False
    serie = [lectura(5 * i, temperatura=5.5) for i in range(5)] + [lectura(30, temperatura=5.6)]
    assert det.lecturas_congeladas(serie, 6) is False


def test_sensor_sin_temperatura_ni_humedad_no_esta_congelado():
    serie = [lectura(5 * i, gps_latitud=-33.0, gps_longitud=-68.0) for i in range(6)]
    assert det.lecturas_congeladas(serie, 6) is False


def test_salto_brusco_dentro_de_la_ventana():
    lecturas = [lectura(0, temperatura=19.0), lectura(10, temperatura=4.0)]
    saltos = det.saltos_bruscos(lecturas, 10.0)
    assert len(saltos) == 1 and saltos[0][2] == 15.0
    fallas = det.fallas_de_sensor(lecturas, REGLAS_POR_DEFECTO)
    assert [f[0] for f in fallas] == [det.FALLA_SALTO]
    assert "de 4 a 19 °C en 10 min" in fallas[0][2]


def test_salto_lejano_en_el_tiempo_o_chico_no_es_falla():
    assert det.saltos_bruscos([lectura(0, temperatura=19.0), lectura(90, temperatura=4.0)], 10) == []
    assert det.saltos_bruscos([lectura(0, temperatura=12.0), lectura(10, temperatura=4.0)], 10) == []


def test_umbrales_informan_la_regla_mas_severa_que_se_cumple():
    vigentes = dict(REGLAS_POR_DEFECTO)
    vigentes[("temperatura", "MAX")] = [(8.0, "Alta", ""), (12.0, "Crítica", "")]
    assert det.evaluar_umbrales(lectura(0, temperatura=10.0), vigentes) == [
        ("Temperatura alta", "Alta", "Temperatura alta: valor 10.00, límite 8.00")]
    assert det.evaluar_umbrales(lectura(0, temperatura=13.0), vigentes) == [
        ("Temperatura alta", "Crítica", "Temperatura alta: valor 13.00, límite 12.00")]


def test_sin_reglas_activas_no_hay_alerta_de_esa_variable():
    vigentes = {k: v for k, v in REGLAS_POR_DEFECTO.items() if k[0] != "temperatura"}
    assert det.evaluar_umbrales(lectura(0, temperatura=30.0), vigentes) == []


def test_simular_falla_produce_lecturas_que_la_deteccion_reconoce():
    from app.services.simulacion_fallas_service import lecturas_de_falla
    for falla, esperado in (("imposible", det.FALLA_VALOR), ("congelada", det.FALLA_CONGELADA),
                            ("salto", det.FALLA_SALTO)):
        datos = lecturas_de_falla(falla, "Temperatura", AHORA)
        lecturas = [SimpleNamespace(fecha_hora=f, id_lectura=str(i), humedad=None, vibracion=None,
                                    gps_latitud=None, gps_longitud=None,
                                    **{"temperatura": None, **v})
                    for i, (f, v) in enumerate(datos)]
        lecturas.sort(key=lambda l: l.fecha_hora, reverse=True)
        assert esperado in [f[0] for f in det.fallas_de_sensor(lecturas, REGLAS_POR_DEFECTO)]
    with pytest.raises(ValueError):
        lecturas_de_falla("salto", "GPS", AHORA)


# ------------------------------------------------------------ reglas de alerta

def test_validar_regla_rangos_y_limites():
    assert reglas_repo.validar_regla("temperatura", "max", "8,5", "Alta") == (
        "temperatura", "MAX", Decimal("8.5"), "Alta")
    with pytest.raises(ValueError, match="entre"):
        reglas_repo.validar_regla("humedad", "MAX", 120, "Media")
    with pytest.raises(ValueError, match="límite"):
        reglas_repo.validar_regla("horas_sin_transmision", "MIN", 24, "Media")
    with pytest.raises(ValueError, match="entero"):
        reglas_repo.validar_regla("lecturas_congeladas", "MAX", "6.5", "Media")
    with pytest.raises(ValueError, match="Severidad"):
        reglas_repo.validar_regla("bateria", "MIN", 20, "Urgente")


def test_umbral_menos_exigente():
    vigentes = {("temperatura", "MAX"): [(12.0, "Crítica", ""), (8.0, "Alta", "")],
                ("temperatura", "MIN"): [(0.0, "Crítica", ""), (2.0, "Alta", "")]}
    assert reglas_repo.umbral(vigentes, "temperatura", "MAX") == 8.0
    assert reglas_repo.umbral(vigentes, "temperatura", "MIN") == 2.0
    assert reglas_repo.umbral(vigentes, "humedad", "MAX", 80.0) == 80.0


def test_crear_regla_valida_antes_de_escribir():
    with patch.object(reglas_repo, "get_postgres_connection") as conectar:
        with pytest.raises(ValueError):
            reglas_repo.crear_regla("temperatura", "MAX", 500, "Alta", "", 1)
    conectar.assert_not_called()


def test_deteccion_lee_las_reglas_de_la_base():
    from app.services import incidentes_service
    with patch.object(incidentes_service, "reglas_vigentes",
                      return_value={("humedad", "MAX"): [(50.0, "Alta", "")]}) as reglas:
        resultado = incidentes_service.detectar_anomalias(lectura(0, humedad=60.0))
    reglas.assert_called_once()
    assert resultado == [("Humedad alta", "Alta", "Humedad alta: valor 60.00, límite 50.00")]


def test_horas_sin_transmision_salen_de_la_regla():
    from app.services import procesos_periodicos_service as procesos
    with patch.object(procesos, "reglas_vigentes",
                      return_value={("horas_sin_transmision", "MAX"): [(6.0, "Alta", "")]}):
        assert procesos.regla_sin_transmision() == (6.0, "Alta")
    with patch.object(procesos, "reglas_vigentes", return_value={}):
        assert procesos.regla_sin_transmision() == (24.0, "Media")


def test_modificar_regla_es_solo_para_internos(capsys):
    from app.services import reglas_alerta_service as srv
    with patch("app.services.autenticacion.obtener_sesion_actual",
               return_value={"id_usuario": 9, "id_cliente": 3}):
        assert srv.modificar_regla_service() is None
    assert "solo para usuarios internos" in capsys.readouterr().out


# ------------------------------------------------------------ mensajes por alerta

def alerta(**extra):
    base = {"_id": "a1", "sensor_id": 7, "contenedor_id": 13, "envio_id": 18,
            "tipo": "Temperatura alta", "severidad": "Alta",
            "descripcion": "Temperatura alta: valor 12.00, límite 8.00",
            "fecha": AHORA, "mensajes_emitidos": False}
    base.update(extra)
    return base


def test_alerta_nueva_notifica_a_internos_y_al_cliente():
    with patch.object(alertas_service, "codigo_contenedor", return_value="TDSU1000130"), \
         patch.object(alertas_service, "destinatarios_alerta",
                      return_value=[(1, True), (5, False)]) as destinatarios, \
         patch.object(alertas_service, "registrar_mensaje_alerta", return_value=True) as mensaje, \
         patch.object(alertas_service, "marcar_mensajes_emitidos") as marcar:
        assert alertas_service.notificar_alerta(alerta()) == 2
    destinatarios.assert_called_once_with(18)
    textos = {c.args[1]: c.args[2] for c in mensaje.call_args_list}
    assert "sensor 7" in textos[1]                 # interno: con el sensor
    assert "sensor" not in textos[5]               # cliente: sin datos técnicos
    assert "envío 18, contenedor TDSU1000130" in textos[5]
    marcar.assert_called_once_with("a1", 2)


def test_alerta_ya_notificada_o_anterior_no_repite_mensajes():
    with patch.object(alertas_service, "destinatarios_alerta") as destinatarios:
        assert alertas_service.notificar_alerta(alerta(mensajes_emitidos=True)) == 0
        sin_campo = alerta()
        del sin_campo["mensajes_emitidos"]       # alertas anteriores al día 3B
        assert alertas_service.notificar_alerta(sin_campo) == 0
    destinatarios.assert_not_called()


def test_mensaje_duplicado_no_se_cuenta():
    from app.repositories import mensajeria_repository as repo
    from pymongo.errors import DuplicateKeyError
    coleccion = MagicMock()
    coleccion.insert_one.side_effect = DuplicateKeyError("dup")
    with patch.object(repo, "coleccion_mensajes", return_value=coleccion):
        assert repo.registrar_mensaje_alerta("a1", 5, "texto") is False


def test_emitir_alerta_no_falla_si_fallan_los_mensajes():
    with patch.object(alertas_service, "registrar_alerta", return_value=alerta(nueva=True)), \
         patch.object(alertas_service, "notificar_alerta", side_effect=RuntimeError("caída")):
        resultado = alertas_service.emitir_alerta(sensor_id=7)
    assert resultado["_id"] == "a1" and resultado["mensajes_creados"] == 0


def test_destinatarios_internos_y_del_cliente_del_envio():
    from app.repositories import mensajeria_repository as repo
    cursor = MagicMock()
    cursor.fetchall.return_value = [(1, True)]
    with patch.object(repo, "get_postgres_connection", return_value=conexion_mock(cursor)):
        repo.destinatarios_alerta(18)
    sql, params = cursor.execute.call_args.args
    assert "num_nonnulls(u.id_cliente, u.id_proveedor, u.id_operador) = 0" in sql
    assert "u.id_cliente = (" in sql and params == {"envio": 18}


def test_bandeja_muestra_el_remitente_del_sistema(capsys):
    from app.services import mensajeria_service as srv
    srv.mostrar_mensaje({"tipo": "Alerta", "remitente_id": None,
                         "remitente_nombre": "Sistema de alertas", "contenido": "x",
                         "fecha_hora": AHORA, "leido": False})
    salida = capsys.readouterr().out
    assert "De: Sistema de alertas" in salida and "ALERTA" in salida


def test_alerta_registrada_marca_si_es_nueva():
    from app.repositories import alerta_repository as repo
    coleccion = MagicMock()
    coleccion.update_one.return_value.upserted_id = "nuevo"
    coleccion.find_one.return_value = {"_id": "nuevo", "mensajes_emitidos": False}
    with patch.object(repo, "coleccion_alertas", return_value=coleccion):
        resultado = repo.registrar_alerta(1, 2, "Temperatura alta", "Alta", "d", "L1", 3)
    assert resultado["nueva"] is True
    insertado = coleccion.update_one.call_args.args[1]["$setOnInsert"]
    assert insertado["mensajes_emitidos"] is False


# ------------------------------------------------------------ predicción (29)

def datos_envio(**extra):
    datos = {"envio_id": 18, "cliente": "Viñedos", "estado": "En tránsito", "prioridad": "Media",
             "fecha_creacion": AHORA - timedelta(days=3), "origen": "Mendoza",
             "destino": "Santiago", "pais_origen": "Argentina", "pais_destino": "Chile",
             "tramos": [(AHORA - timedelta(days=1), AHORA + timedelta(days=2), "Mendoza", "Santiago")],
             "incidentes": []}
    datos.update(extra)
    return datos


def alerta_clima(ubicacion, severidad, desde, hasta, fenomeno="Nevada"):
    return {"_id": f"{ubicacion}-{desde}", "ubicacion": ubicacion,
            "ubicacion_normalizada": clima_repo.normalizar_lugar(ubicacion),
            "fenomeno": fenomeno, "severidad": severidad,
            "fecha_desde": desde.isoformat(), "fecha_hasta": hasta.isoformat(),
            "inicio": datetime(desde.year, desde.month, desde.day, 3, tzinfo=timezone.utc),
            "fin": datetime(hasta.year, hasta.month, hasta.day, 3, tzinfo=timezone.utc) + timedelta(days=1)}


def test_probabilidad_combinada_a_mano():
    # Ruta 50 %, clima Alta 45 %, incidente Alta 30 %:
    # 1 - 0,5 x 0,55 x 0,7 = 0,8075 -> 80,8 % -> ALTO
    datos = datos_envio(
        historial_ruta={"ruta": "Mendoza -> Santiago", "envios": 4, "atrasados": 2,
                        "tasa": 0.5, "fuente": "ruta"},
        alertas_climaticas=[alerta_clima("Mendoza", "Alta", date(2026, 10, 30), date(2026, 11, 2))],
        incidentes=[("Alta", "Abierto")])
    resultado = pred.calcular_riesgo(datos, AHORA)
    assert resultado["probabilidad_demora"] == 80.8
    assert resultado["riesgo_climatico"] == "ALTO"
    assert resultado["nivel_riesgo"] == "ALTO"
    assert resultado["riesgo_operativo"] == "BAJO"
    assert resultado["metodo"] == "reglas_heuristicas_v4"
    assert {f["factor"] for f in resultado["factores_probabilidad"]} == {
        "Historial de la ruta", "Clima", "Incidente Alta"}
    assert any("Nevada en Mendoza" in m for m in resultado["motivos"])


def test_entidad_prediccion_de_riesgo_tiene_los_campos_de_la_consigna():
    resultado = pred.calcular_riesgo(datos_envio(alertas_climaticas=[]), AHORA)
    for campo in ("envio_id", "riesgo_climatico", "riesgo_operativo",
                  "probabilidad_demora", "fecha_calculo"):
        assert campo in resultado
    assert resultado["riesgo_climatico"] == "SIN ALERTAS"


def test_llegada_vencida_es_demora_confirmada():
    datos = datos_envio(tramos=[(AHORA - timedelta(days=3), AHORA - timedelta(hours=27),
                                 "Mendoza", "Santiago")], alertas_climaticas=[])
    resultado = pred.calcular_riesgo(datos, AHORA)
    assert resultado["probabilidad_demora"] == 100.0 and resultado["nivel_riesgo"] == "ALTO"


def test_clima_de_otra_ciudad_o_de_otro_periodo_no_afecta():
    datos = datos_envio()
    lejos = alerta_clima("Ushuaia", "Extrema", date(2026, 10, 30), date(2026, 11, 2))
    vencida = alerta_clima("Mendoza", "Alta", date(2026, 10, 1), date(2026, 10, 3))
    assert pred.alertas_que_afectan(datos, [lejos, vencida], AHORA) == []


def test_clima_por_pais_y_ciudad_sin_acentos():
    datos = datos_envio(destino="Córdoba", pais_destino="Argentina",
                        tramos=[(AHORA - timedelta(hours=5), AHORA + timedelta(hours=20),
                                 "Rosario", "Cordoba")])
    por_pais = alerta_clima("ARGENTINA", "Media", date(2026, 10, 31), date(2026, 10, 31))
    por_ciudad = alerta_clima("cordoba", "Baja", date(2026, 11, 1), date(2026, 11, 1))
    assert len(pred.alertas_que_afectan(datos, [por_pais, por_ciudad], AHORA)) == 2


def test_envio_demorado_sigue_expuesto_al_clima_de_hoy():
    # Llegada estimada ayer, sigue en tránsito: la alerta de hoy lo afecta.
    datos = datos_envio(tramos=[(AHORA - timedelta(days=3), AHORA - timedelta(days=1),
                                 "Mendoza", "Santiago")])
    hoy = alerta_clima("Santiago", "Media", date(2026, 10, 31), date(2026, 11, 1))
    assert len(pred.alertas_que_afectan(datos, [hoy], AHORA)) == 1


def test_historial_de_rutas_entregas_tarde_y_retrasos():
    entregados = [
        (1, "Mendoza", "Santiago", AHORA, AHORA - timedelta(hours=1)),    # a tiempo
        (2, "Mendoza", "Santiago", AHORA, AHORA + timedelta(hours=5)),    # tarde
        (3, "mendoza", "Santiago", AHORA, AHORA - timedelta(hours=2)),    # RETRASO informado
        (4, "Buenos Aires", "Ushuaia", AHORA, AHORA - timedelta(hours=1)),
    ]
    historial = pred.calcular_historial_rutas(entregados, {3: (1, "Paso cerrado")})
    ruta = historial["rutas"][("mendoza", "santiago")]
    assert (ruta["envios"], ruta["atrasados"]) == (3, 2)
    assert historial["general"] == {"envios": 4, "atrasados": 2}
    propio = pred.historial_de_ruta({"origen": "Mendoza", "destino": "Santiago"}, historial)
    assert propio["fuente"] == "ruta" and propio["tasa"] == pytest.approx(2 / 3)
    sin_historial = pred.historial_de_ruta({"origen": "Asunción", "destino": "Córdoba"}, historial)
    assert sin_historial["fuente"] == "general" and sin_historial["tasa"] == 0.5


def test_sin_fechas_la_probabilidad_solo_sube_el_nivel_si_es_alta():
    base = dict(tramos=[], alertas_climaticas=[])
    medio = pred.calcular_riesgo(datos_envio(incidentes=[("Alta", "Abierto")], **base), AHORA)
    assert medio["nivel_riesgo"] == "INFORMACIÓN INSUFICIENTE"
    alto = pred.calcular_riesgo(datos_envio(
        incidentes=[("Crítica", "Abierto"), ("Crítica", "Abierto")], **base), AHORA)
    assert alto["probabilidad_demora"] == 64.0 and alto["nivel_riesgo"] == "ALTO"


def test_envio_entregado_no_aplica_clima():
    resultado = pred.calcular_riesgo(datos_envio(estado="Entregado", alertas_climaticas=[
        alerta_clima("Mendoza", "Alta", date(2026, 10, 30), date(2026, 11, 2))]), AHORA)
    assert resultado["riesgo_climatico"] == "NO APLICA" and resultado["probabilidad_demora"] == 0


def test_validacion_de_alerta_climatica():
    with pytest.raises(ValueError, match="Severidad"):
        clima_repo.validar("Mendoza", "Nevada", "Grave", date(2026, 10, 30), date(2026, 11, 1))
    with pytest.raises(ValueError, match="posterior"):
        clima_repo.validar("Mendoza", "Nevada", "Alta", date(2026, 11, 2), date(2026, 11, 1))
    with pytest.raises(ValueError, match="ubicación"):
        clima_repo.validar(" ", "Nevada", "Alta", date(2026, 10, 30), date(2026, 11, 1))
    assert clima_repo.normalizar_lugar("  Córdoba ") == "cordoba"


# ------------------------------------------------------------ reporte predictivo (34)

def test_predictivo_cobrable_no_pide_periodo():
    from app.services import reportes_cobrables_service as cobrables
    params = cobrables.validar_parametros("PREDICTIVO", {}, hoy_=date(2026, 10, 31))
    assert params == {"fecha_corte": "2026-10-31"}
    assert cobrables.describir_parametros(params) == ["Situación al: 31/10/2026"]


def test_predictivo_cobrable_solo_del_cliente_y_sin_columna_cliente():
    from app.services import reportes_cobrables_service as cobrables
    from app.utils.exportar_reportes import Tabla
    tabla = Tabla("x", ["Envío", "Cliente", "Ruta"], [(18, "Viñedos", "Mendoza -> Santiago")])
    with patch("app.services.reportes_service.reporte_riesgo_envios", return_value=tabla) as interno:
        resultado = cobrables.generar_predictivo(5, {"fecha_corte": "2026-10-31"})
    interno.assert_called_once_with(5)
    assert resultado.columnas == ["Envío", "Ruta"] and resultado.filas == [(18, "Mendoza -> Santiago")]
    assert resultado.vacio == "No hay envíos en curso"


def test_reporte_riesgo_ordena_por_nivel_y_probabilidad():
    from app.services import reportes_service as rs
    envios = [(14, "A", "X", "Y", "En tránsito"), (18, "B", "M", "S", "En tránsito"),
              (16, "C", "X", "Y", "Pendiente")]
    preds = {14: {"nivel_riesgo": "MEDIO", "probabilidad_demora": 40.0, "fecha_calculo": AHORA,
                  "factores_probabilidad": [{"factor": "Clima", "probabilidad": 0.25}]},
             18: {"nivel_riesgo": "ALTO", "probabilidad_demora": 100.0, "fecha_calculo": AHORA,
                  "factores_probabilidad": [{"factor": "Llegada estimada vencida", "probabilidad": 1.0}]}}
    with patch.object(rs.repo, "envios_en_curso", return_value=envios), \
         patch("app.repositories.predicciones_repository.ultimas_predicciones", return_value=preds):
        tabla = rs.reporte_riesgo_envios()
    assert [f[0] for f in tabla.filas] == [18, 14, 16]
    assert tabla.filas[0][5] == "100,0 %" and tabla.filas[2][4] == "Sin predicción"
    assert tabla.filas[0][8] == "Llegada estimada vencida (100%)"


def test_rutas_que_suelen_atrasarse():
    from app.services import reportes_service as rs
    historial = {"rutas": {("m", "s"): {"ruta": "Mendoza -> Santiago", "envios": 4, "atrasados": 2},
                           ("a", "b"): {"ruta": "Asunción -> Buenos Aires", "envios": 1, "atrasados": 0}},
                 "general": {"envios": 5, "atrasados": 2}}
    with patch("app.services.predicciones_service.historial_rutas", return_value=historial):
        tabla = rs.reporte_rutas_atraso()
    assert tabla.filas[0] == ("Mendoza -> Santiago", 4, 2, 50.0, "Sí")
    assert tabla.filas[1][4].startswith("No")
    assert "2 de 5" in tabla.notas[1]


# ------------------------------------------------------------ sesiones (3)

def test_cerrar_sesion_ajena_registra_quien_y_excluye_la_propia():
    from app.repositories import sesion_repository as repo
    cursor = MagicMock()
    cursor.rowcount = 1
    with patch.object(repo, "get_postgres_connection", return_value=conexion_mock(cursor)):
        assert repo.cerrar_sesion_ajena_db(30, 4) is True
    sql, params = cursor.execute.call_args.args
    assert "cerrada_por = %s" in sql and "id_usuario <> %s" in sql
    assert params == (4, 30, 4)


def test_el_administrador_no_cierra_su_propia_sesion_desde_la_lista(capsys):
    from app.services import sesion_service as srv
    sesiones = [(30, 4, "Ana", "Admin", "a@x", AHORA, "Interno")]
    with patch("builtins.input", side_effect=["1"]), \
         patch.object(srv, "cerrar_sesion_ajena_db") as cerrar:
        assert srv.cerrar_sesion_de_otro(sesiones, {"id_sesion": 30, "id_usuario": 4}) is False
    cerrar.assert_not_called()
    assert "Cerrar sesión" in capsys.readouterr().out


def test_el_administrador_cierra_una_sesion_ajena():
    from app.services import sesion_service as srv
    sesiones = [(31, 7, "Juan", "Cliente", "j@x", AHORA, "Cliente: Viñedos")]
    with patch("builtins.input", side_effect=["1", "S"]), \
         patch.object(srv, "cerrar_sesion_ajena_db", return_value=True) as cerrar:
        assert srv.cerrar_sesion_de_otro(sesiones, {"id_sesion": 30, "id_usuario": 4}) is True
    cerrar.assert_called_once_with(31, 4)


def test_el_usuario_desalojado_ve_el_aviso_una_vez():
    from app.services import autenticacion
    cursor = MagicMock()
    cursor.fetchone.return_value = None
    autenticacion.establecer_sesion(31, 7)
    with patch.object(autenticacion, "get_postgres_connection", return_value=conexion_mock(cursor)), \
         patch("app.repositories.sesion_repository.cerrada_por_otro", return_value=True):
        assert autenticacion.obtener_sesion_actual() is None
    assert autenticacion.tomar_aviso_cierre() == "Tu sesión fue cerrada por un administrador."
    assert autenticacion.tomar_aviso_cierre() is None


def test_sesiones_activas_exige_administrador_interno():
    from app.services import sesion_service as srv
    with patch.object(srv, "verificar_permiso", return_value=False), \
         patch("builtins.input"), patch.object(srv, "listar_sesiones_activas") as listar:
        srv.consultar_sesiones_activas_service()
    listar.assert_not_called()


# ------------------------------------------------------------ sensores y tarifas

def test_asociar_contenedor_reactiva_solo_sensores_apagados_por_entrega():
    from app.repositories import envio_contenedor_repository as repo
    cursor = MagicMock()
    cursor.fetchone.return_value = (18,)
    with patch.object(repo, "get_postgres_connection", return_value=conexion_mock(cursor)):
        assert repo.asociar_contenedor_db(18, 13) is True
    sql, params = cursor.execute.call_args_list[1].args
    assert "SET estado = 'Activo', motivo_inactivo = NULL" in sql
    assert "motivo_inactivo LIKE 'Entrega del envío %%'" in sql and params == (13,)


def test_listar_cargas_envio_une_tipo_carga_por_codigo():
    from app.repositories import tarifas_repository as repo
    cursor = MagicMock()
    cursor.fetchall.return_value = [(1, "REFRIGERADA", "Carga refrigerada", Decimal("1000"), False, None)]
    with patch.object(repo, "get_postgres_connection", return_value=conexion_mock(cursor)):
        filas = repo.listar_cargas_envio(18)
    sql, params = cursor.execute.call_args.args
    assert "ON tc.codigo = ec.tipo_carga" in sql and "USING" not in sql
    assert params == (18,) and filas[0][2] == "Carga refrigerada"


# ------------------------------------------------------------ textos de pantalla

def test_tabla_no_muestra_la_fuente_y_usa_mensaje_vacio(capsys):
    from app.utils.exportar_reportes import Tabla, imprimir_tabla, mensaje_vacio
    tabla = Tabla("Envíos demorados", ["Envío"], [], "PostgreSQL + MongoDB", vacio="No hay envíos demorados")
    imprimir_tabla(tabla, mensaje_vacio(tabla, cliente=True))
    salida = capsys.readouterr().out
    assert "PostgreSQL" not in salida and "Fuente" not in salida
    assert "No hay envíos demorados para el cliente elegido." in salida


def test_cantidades_enteras_e_importes_con_decimales():
    from app.utils.exportar_reportes import texto
    assert texto(Decimal("3")) == "3"
    assert texto(Decimal("1500.00")) == "1,500.00"
    assert texto(Decimal("0.67")) == "0.67"


def test_parametros_en_lenguaje_natural():
    from app.services import reportes_cobrables_service as cobrables
    with patch("app.services.alertas_service.codigo_contenedor", return_value="MSCU1234571"):
        lineas = cobrables.describir_parametros(
            {"desde": "2026-05-01", "hasta": "2026-10-31", "id_contenedor": 7})
    assert lineas == ["Período: 01/05/2026 al 31/10/2026", "Contenedor: MSCU1234571"]


def test_ver_reporte_sin_hash_ni_diccionario(capsys):
    from app.services import reportes_pantallas as pantallas
    reporte = {"id_reporte": 1, "cliente": "Viñedos", "tipo": "PUNTUALIDAD", "formato": "CSV",
               "estado": "FACTURADO", "usuario": "Ana", "fecha_solicitud": AHORA,
               "parametros": {"desde": "2026-05-01", "hasta": "2026-10-31"},
               "importe_base": Decimal("12000.00"), "id_factura": 14,
               "total_factura": Decimal("14520.00"), "archivo": "reportes_generados/1.csv",
               "filas": 5, "hash_archivo": "ab" * 32, "error": None}
    with patch.object(pantallas, "nombre_tipo", return_value="Puntualidad de mis envíos"):
        pantallas.mostrar_reporte(reporte)
    salida = capsys.readouterr().out
    assert "SHA" not in salida and "abab" not in salida and "{" not in salida
    assert "Período: 01/05/2026 al 31/10/2026" in salida
    assert "Puntualidad de mis envíos" in salida and "PUNTUALIDAD" not in salida


BASES = re.compile(r"MongoDB|Mongo\b|PostgreSQL|Postgres\b|Cassandra|Neo4j|SHA-256")


def _textos_de_pantalla(ruta):
    """Literales de texto pasados a print() o input() en un archivo."""
    arbol = ast.parse(Path(ruta).read_text(encoding="utf-8"))
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Call) and getattr(nodo.func, "id", None) in ("print", "input"):
            for sub in ast.walk(nodo):
                if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                    yield nodo.lineno, sub.value


def test_ninguna_pantalla_menciona_bases_de_datos():
    raiz = Path(__file__).resolve().parents[1] / "app"
    hallazgos = [
        f"{ruta.relative_to(raiz)}:{linea}: {texto!r}"
        for carpeta in ("services", "ui", "utils")
        for ruta in sorted((raiz / carpeta).glob("*.py"))
        for linea, texto in _textos_de_pantalla(ruta)
        if BASES.search(texto)
    ]
    assert hallazgos == []


# ------------------------------------------------------------ correcciones de prueba

def test_alertas_de_la_misma_ubicacion_usan_solo_la_mas_severa():
    media = alerta_clima("Buenos Aires", "Media", date(2026, 10, 31), date(2026, 11, 1), "Tormenta")
    alta = alerta_clima("buenos aires", "Alta", date(2026, 10, 30), date(2026, 11, 2), "Tormenta fuerte")
    otra = alerta_clima("Miami", "Baja", date(2026, 10, 31), date(2026, 11, 1), "Lluvia")
    elegidas = pred.mas_severa_por_ubicacion([media, alta, otra])
    assert sorted(a["severidad"] for a in elegidas) == ["Alta", "Baja"]

    datos = datos_envio(origen="Buenos Aires", destino="Miami", pais_origen="Argentina",
                        pais_destino="Estados Unidos",
                        tramos=[(AHORA - timedelta(days=1), AHORA + timedelta(days=2),
                                 "Buenos Aires", "Miami")],
                        alertas_climaticas=[media, alta])
    resultado = pred.calcular_riesgo(datos, AHORA)
    # Una sola alerta (Alta, 0,45): no se combina con la Media de la misma ubicación.
    assert resultado["probabilidad_demora"] == 45.0
    assert [a["severidad"] for a in resultado["alertas_climaticas"]] == ["Alta"]
    assert sum("Alerta climática" in m for m in resultado["motivos"]) == 1


def test_texto_de_la_probabilidad():
    assert pred.texto_probabilidad({"probabilidad_demora": 66.7, "nivel_riesgo": "ALTO"}) == "66,7 %"
    assert pred.texto_probabilidad({"probabilidad_demora": 58.3,
                                    "nivel_riesgo": "INFORMACIÓN INSUFICIENTE",
                                    "datos_suficientes": False}).startswith("no se puede estimar")
    assert pred.texto_probabilidad({"probabilidad_demora": 64.0, "nivel_riesgo": "ALTO",
                                    "datos_suficientes": False}).startswith("al menos 64,0 %")
    assert pred.texto_probabilidad({"puntaje_riesgo": 25}).startswith("sin dato")


def test_pantallas_de_prediccion_muestran_la_probabilidad_y_no_el_puntaje(capsys):
    resultado = pred.calcular_riesgo(datos_envio(incidentes=[("Alta", "Abierto")],
                                                 alertas_climaticas=[]), AHORA)
    pred.mostrar_prediccion(resultado)
    salida = capsys.readouterr().out
    assert "Probabilidad de demora: 30,0 %" in salida and "/100" not in salida
    with patch.object(pred, "listar_envios_analisis", return_value=[(18, "V", "M", "S", "En tránsito")]), \
         patch.object(pred, "actualizar_predicciones_activas", return_value={
             "guardadas": 1, "riesgos_altos": 1, "informacion_insuficiente": 0, "errores": 0,
             "resultados": [{"envio_id": 18, "guardada": True, "nivel_riesgo": "ALTO",
                             "puntaje": 25, "probabilidad": "66,7 %"}]}), \
         patch("builtins.input", side_effect=["S", ""]):
        pred.actualizar_predicciones_service()
    salida = capsys.readouterr().out
    assert "Envío 18: ALTO (66,7 %)" in salida and "/100" not in salida


def test_mensaje_de_alerta_sin_none_y_con_codigo_de_contenedor():
    interno, cliente = alertas_service.textos_mensaje(
        alerta(envio_id=None, fecha=None, descripcion=None), "MSCU1234587")
    assert "None" not in interno + cliente
    assert "contenedor MSCU1234587" in cliente


def test_congelada_menciona_solo_lo_que_mide_el_sensor():
    serie = [lectura(5 * i, temperatura=5.5) for i in range(6)]
    descripcion = det.fallas_de_sensor(serie, REGLAS_POR_DEFECTO)[0][2]
    assert "temperatura 5.5" in descripcion and "humedad" not in descripcion and "None" not in descripcion


def test_sin_transmision_identifica_el_contenedor_por_codigo():
    from app.services import procesos_periodicos_service as procesos
    sensor = (4, 2, "MSCU1234587", "GPS", None, None, "Activo")
    with patch.object(procesos, "listar_sensores", return_value=[sensor]), \
         patch.object(procesos, "consultar_ultima_lectura_db", return_value=None), \
         patch("app.services.incidentes_service.buscar_envios_activos_de_contenedor", return_value=[]), \
         patch.object(procesos, "emitir_alerta") as emitir:
        procesos.detectar_sensores_inactivos_automatico(ahora=AHORA)
    descripcion = emitir.call_args.kwargs["descripcion"]
    assert "contenedor MSCU1234587" in descripcion and "contenedor 2" not in descripcion
    assert "sensor de GPS" in descripcion


def test_sesion_cerrada_avisa_antes_de_validar_la_opcion(capsys):
    from app.ui import menu_principal
    usuario = {"nombre": "Ana", "apellido": "A", "rol": "Admin", "nivel_permisos": 5}
    with patch("builtins.input", return_value="99"), \
         patch.object(menu_principal, "obtener_sesion_actual", return_value=None):
        assert menu_principal.mostrar_menu_interno(usuario) is False
    assert "Opción inválida" not in capsys.readouterr().out


def test_verificar_permiso_muestra_el_aviso_de_cierre(capsys):
    from app.services import autenticacion
    autenticacion._aviso_cierre = "Tu sesión fue cerrada por un administrador."
    with patch.object(autenticacion, "obtener_sesion_actual", return_value=None):
        assert autenticacion.verificar_permiso(1) is False
    assert "cerrada por un administrador" in capsys.readouterr().out
    assert autenticacion.tomar_aviso_cierre() is None


def test_predicciones_no_duplica_el_ranking_de_reportes():
    texto = (Path(__file__).resolve().parents[1] / "app" / "ui" / "menu_predicciones.py").read_text(encoding="utf-8")
    assert "Ranking de clientes por envíos" not in texto
    assert 'REPORTES_RANKINGS["2"]' in texto


def test_nombre_del_tipo_de_sensor_respeta_las_siglas():
    assert det.nombre_tipo_sensor("GPS") == "GPS"
    assert det.nombre_tipo_sensor("Humedad") == "humedad"
    assert det.nombre_tipo_sensor(" Vibración ") == "vibración"


def test_descripcion_sin_transmision_en_hora_argentina():
    texto = det.descripcion_sin_transmision(
        "GPS", "MSCU1234587", datetime(2026, 10, 27, 11, 42, tzinfo=timezone.utc), 24.0)
    assert texto == ("El sensor de GPS del contenedor MSCU1234587 no transmite desde "
                     "27/10/2026 08:42. Umbral: 24 horas.")
    assert det.descripcion_sin_transmision("Humedad", "TDSU1000124") == (
        "El sensor de humedad del contenedor TDSU1000124 no tiene lecturas registradas.")
