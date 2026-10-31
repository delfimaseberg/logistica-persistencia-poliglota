"""Día 3A: reportes internos, reportes cobrables, exportación y filtros."""

from contextlib import ExitStack
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.repositories import facturacion_repository as fact_repo
from app.repositories import reportes_repository as repo
from app.services import autenticacion
from app.services import reportes_cobrables_service as cobrables
from app.services import reportes_pantallas as pantallas
from app.services import reportes_service as rs
from app.utils import exportar_reportes as exp

UTC = timezone.utc
AHORA = datetime(2026, 10, 30, 20, tzinfo=UTC)
D1, D2 = date(2026, 8, 1), date(2026, 10, 30)


def t(texto):
    return datetime.fromisoformat(texto).replace(tzinfo=UTC)


# --------------------------------------------------------- definiciones

@pytest.mark.parametrize("estado, estimada, entrega, esperado", [
    ("Entregado", t("2026-10-05 18:00"), t("2026-10-05 18:00"), "A tiempo"),
    ("Entregado", t("2026-10-05 18:00"), t("2026-10-05 18:01"), "Tarde"),
    ("En tránsito", t("2026-10-28 18:00"), None, "Demorado"),
    ("En tránsito", t("2026-11-02 18:00"), None, "En curso"),
    ("Cancelado", t("2026-10-01 00:00"), None, "Cancelado"),
    ("Pendiente", None, None, "Sin tramos"),
])
def test_situacion_sin_tolerancia(estado, estimada, entrega, esperado):
    assert rs.situacion(estado, estimada, entrega, AHORA) == esperado


# --------------------------------------------------------- 35 operativos

def test_envios_por_pais_usa_pais_de_destino_y_filtra_por_cliente():
    with patch.object(repo, "_q", return_value=[]) as consulta:
        rs.reporte_envios_por_pais(D1, D2, 7)
    sql, params = consulta.call_args.args
    assert "COALESCE(e.pais_destino, 'Sin dato')" in sql
    assert "paises_origen" in sql
    assert params == (D1, D2, 7, 7)


def test_demorados_combina_postgres_y_retrasos_de_mongo():
    fila = (18, "Viñedos", "Mendoza", "Santiago", "Argentina", "Chile", "En tránsito",
            t("2026-10-28 18:00"), Decimal("50.25"))
    with patch.object(repo, "envios_demorados", return_value=[fila]), \
         patch.object(rs, "retrasos_por_envio", return_value={18: (1, "Tormenta")}):
        tabla = rs.reporte_envios_demorados()
    assert tabla.filas == [(18, "Viñedos", "Mendoza -> Santiago", "Argentina -> Chile",
                            "En tránsito", fila[7], 50.2, 1, "Tormenta")]
    assert "MongoDB" in tabla.fuente


def test_incidentes_abiertos_excluye_cerrados():
    with patch.object(repo, "_q", return_value=[]) as consulta:
        rs.reporte_incidentes_abiertos()
    assert "NOT IN ('cerrado', 'resuelto')" in consulta.call_args.args[0]


# ------------------------------------------------------ 36 / 38 tiempos

def entregado(id_envio, cliente, creado, entrega, estimada, medios=("Terrestre",)):
    return (id_envio, cliente, "Mendoza", "Santiago", "Argentina", "Chile",
            t(creado), t(entrega), t(estimada), list(medios))


ENTREGADOS = [
    entregado(1, "A", "2026-08-03 09:00", "2026-08-07 17:00", "2026-08-07 18:00"),
    entregado(2, "A", "2026-09-01 09:00", "2026-09-07 16:00", "2026-09-04 18:00"),
    entregado(3, "B", "2026-10-01 09:00", "2026-10-02 09:00", "2026-10-03 00:00", ("Aéreo",)),
]
TRANSITO = {1: (t("2026-08-05 08:00"), None), 2: (t("2026-09-02 08:00"), None)}


def test_tiempos_maximos_y_minimos_por_cliente():
    with patch.object(repo, "envios_entregados", return_value=ENTREGADOS), \
         patch.object(rs, "tiempos_por_envio", return_value=TRANSITO):
        tabla = rs.reporte_tiempos_extremos(D1, D2)
    a = next(f for f in tabla.filas if f[0] == "A")
    # total: 104 h y 151 h; tránsito: 57 h y 128 h
    assert a == ("A", 2, 104.0, 151.0, 57.0, 128.0)
    b = next(f for f in tabla.filas if f[0] == "B")
    assert b == ("B", 1, 24.0, 24.0, None, None)      # sin evento EN_TRANSITO


def test_tiempos_promedio_por_cliente_ruta_y_medio():
    with patch.object(repo, "envios_entregados", return_value=ENTREGADOS), \
         patch.object(rs, "tiempos_por_envio", return_value=TRANSITO):
        tabla = rs.reporte_tiempos_promedio(D1, D2)
    filas = {(f[0], f[1]): f for f in tabla.filas}
    assert filas[("Cliente", "A")][3] == 127.5
    assert filas[("Medio", "Aéreo")][2] == 1
    assert filas[("Ruta", "Mendoza -> Santiago")][2] == 3


# ---------------------------------------------------------- 37 / 39

def test_promedio_incidentes_por_tres_agrupaciones():
    with patch.object(repo, "promedio_incidentes", return_value=[("X", 4, 2, Decimal("0.50"))]) as p:
        tabla = rs.reporte_promedio_incidentes(D1, D2)
    assert [c.args[2] for c in p.call_args_list] == ["pais", "estado", "cliente"]
    assert {f[0] for f in tabla.filas} == {"País destino", "Estado", "Cliente"}


def test_promedio_incidentes_rechaza_agrupacion_desconocida():
    with pytest.raises(ValueError):
        repo.promedio_incidentes(D1, D2, "medio")


def test_costos_por_medio_compara_cobrado_y_costo():
    with patch.object(repo, "ventas_por_medio", return_value=[
            ("Terrestre", 4, Decimal("480000")), ("Cargo base por envío", 3, Decimal("45000"))]), \
         patch.object(repo, "costos_operadores_por_medio", return_value=[
            ("Terrestre", 4, Decimal("280000")), ("Marítimo", 1, Decimal("280000"))]):
        tabla = rs.reporte_costos_por_medio(D1, D2)
    filas = {f[0]: f for f in tabla.filas}
    assert filas["Terrestre"][5] == Decimal("200000") and filas["Terrestre"][6] == 41.7
    assert filas["Marítimo"][2] == Decimal("0") and filas["Marítimo"][5] == Decimal("-280000")
    assert filas["Cargo base por envío"][4] is None


# ---------------------------------------------------------- 27 / 28 / 31

def test_ranking_volumen_usa_contenedores_capacidad_y_peso():
    with patch.object(repo, "_q", return_value=[]) as consulta:
        rs.reporte_ranking_volumen(D1, D2)
    sql = consulta.call_args.args[0]
    assert "SUM(k.capacidad)" in sql and "SUM(ca.peso_kg)" in sql
    assert "ORDER BY 6 DESC, 5 DESC" in sql


def test_ranking_rutas_solo_rutas_con_incidentes():
    with patch.object(repo, "_q", return_value=[]) as consulta:
        rs.reporte_ranking_rutas(D1, D2)
    assert "HAVING COUNT(i.id_incidente) > 0" in consulta.call_args.args[0]


def test_desempeno_por_ruta_mes_y_operador_de_neo4j():
    with patch.object(repo, "envios_entregados", return_value=ENTREGADOS), \
         patch("app.repositories.grafo_repository.operadores_por_envio",
               return_value={1: [(1, "Andinos", "Terrestre")], 2: [(1, "Andinos", "Terrestre")],
                             3: [(3, "AeroCarga", "Aéreo")]}):
        tabla = rs.reporte_desempeno(D1, D2, ahora=AHORA)
    filas = {(f[0], f[1]): f for f in tabla.filas}
    assert filas[("Operador", "Andinos")][2:6] == (2, 1, 1, 50.0)
    assert filas[("Operador", "Andinos")][6] == 70.0      # 2026-09-07 16:00 vs 09-04 18:00
    assert filas[("Operador", "AeroCarga")][3] == 1
    assert ("Mes", "2026-09") in filas
    assert "Neo4j" in tabla.fuente


# ------------------------------------------------- reportes cobrables

def test_parametros_validados():
    p = cobrables.validar_parametros("PUNTUALIDAD", {"desde": "2026-08-01", "hasta": "2026-10-30",
                                                     "ruta": " Mendoza "}, hoy_=D2)
    assert p == {"desde": "2026-08-01", "hasta": "2026-10-30", "ruta": "Mendoza"}
    for malos, texto in ([{"desde": "2026-10-31", "hasta": "2026-10-30"}, "posterior"],
                         [{"desde": "2026-10-01", "hasta": "2026-11-01"}, "futura"],
                         [{"desde": "2025-01-01", "hasta": "2026-10-30"}, "366"],
                         [{"desde": "x", "hasta": "2026-10-30"}, "formato"]):
        with pytest.raises(ValueError, match=texto):
            cobrables.validar_parametros("PUNTUALIDAD", malos, hoy_=D2)
    with pytest.raises(ValueError, match="contenedor"):
        cobrables.validar_parametros("OPERADORES", {"desde": "2026-10-01", "hasta": "2026-10-02",
                                                    "id_contenedor": "abc"}, hoy_=D2)
    with pytest.raises(ValueError, match="Tipo"):
        cobrables.validar_parametros("OTRO", {}, hoy_=D2)


PARAMS = {"desde": "2026-08-01", "hasta": "2026-10-30"}


def test_incidentes_solo_del_cliente_y_alertas_de_sus_contenedores():
    alerta = {"fecha": datetime(2026, 10, 30, 21, 38), "envio_id": 18, "contenedor_id": 40,
              "tipo": "Temperatura alta", "severidad": "Alta", "estado": "Activa",
              "descripcion": "11.4 °C"}
    with patch.object(repo, "incidentes_cliente", return_value=[
            (t("2026-10-27 12:00"), 18, "Mendoza -> Santiago", "Retraso", "Alta", "Abierto", "Nieve")]) as inc, \
         patch.object(repo, "contenedores_cliente", return_value=[(40, "TDSU1", "Refrigerado", 18, None, None)]) as cont, \
         patch("app.repositories.alerta_repository.listar_alertas_contenedores",
               return_value=[alerta]) as alertas:
        tabla = cobrables.generar_incidentes(5, PARAMS)
    assert inc.call_args.args[0] == 5 and cont.call_args.args[0] == 5
    assert alertas.call_args.args[0] == [40]          # solo sus contenedores
    assert [f[0] for f in tabla.filas] == ["Incidente", "Alerta IoT"]
    assert tabla.filas[1][1].tzinfo is not None       # fecha de MongoDB normalizada


def test_puntualidad_marca_situacion_y_horas():
    filas = [(5, "Mendoza", "Santiago", "Argentina", "Chile", "Entregado", t("2026-09-01 12:00"),
              t("2026-09-04 21:00"), t("2026-09-07 19:00")),
             (18, "Mendoza", "Santiago", "Argentina", "Chile", "En tránsito", t("2026-10-25 12:00"),
              t("2026-10-28 21:00"), None)]
    with patch.object(repo, "puntualidad_cliente", return_value=filas) as consulta, \
         patch.object(cobrables, "retrasos_por_envio", return_value={5: (1, "Nevadas")}):
        tabla = cobrables.generar_puntualidad(5, {**PARAMS, "ruta": "Mendoza"}, ahora=AHORA)
    assert consulta.call_args.args == (5, D1, D2, "Mendoza")
    assert tabla.filas[0][6:9] == ("Tarde", 70.0, 1)
    assert tabla.filas[1][6:8] == ("Demorado", 47.0)
    assert "Demorado: 1" in tabla.notas[0] and "Tarde: 1" in tabla.notas[0]


def test_operadores_desde_neo4j_solo_envios_del_cliente():
    with patch.object(repo, "ids_envios_cliente", return_value=[5, 6]) as ids, \
         patch("app.repositories.grafo_repository.operadores_de_contenedores_cliente",
               return_value=[{"contenedor": "TDSU1", "id_envio": 5, "id_tramo": 4, "medio": "Terrestre",
                              "origen": "Mendoza", "destino": "Santiago",
                              "salida": "2026-08-05T08:00:00-03:00", "operador": "Andinos"}]) as grafo:
        tabla = cobrables.generar_operadores(5, {**PARAMS, "id_contenedor": 40})
    assert ids.call_args.args == (5, D1, D2)
    assert grafo.call_args.args == (5, [5, 6], 40)
    assert tabla.filas[0][-1] == "Andinos" and tabla.filas[0][6] == "2026-08-05 08:00"


def test_condiciones_de_carga_desde_cassandra_por_contenedor():
    def lectura(minuto, temp=None, hum=None, lat=None):
        return SimpleNamespace(fecha_hora=t(f"2026-10-02 10:{minuto:02d}"), temperatura=temp,
                               humedad=hum, gps_latitud=lat, gps_longitud=-68.0 if lat else None)
    lecturas = [lectura(0, temp=4.0), lectura(1, temp=9.5), lectura(2, hum=85.0),
                lectura(3, lat=-32.9), lectura(4, lat=-33.4)]
    contenedor = (40, "TDSU1000037", "Refrigerado", 7, t("2026-10-01 12:00"), t("2026-10-06 21:00"))
    # Umbrales de las reglas de alerta: 2-8 °C y humedad máxima 80 %.
    with patch.object(repo, "contenedores_cliente", return_value=[contenedor]) as cont, \
         patch.object(cobrables, "limites_carga", return_value=(2.0, 8.0, 80.0)), \
         patch("app.repositories.lectura_iot_repository.consultar_lecturas_contenedor_periodo",
               return_value=lecturas) as cass:
        tabla = cobrables.generar_condiciones_carga(5, PARAMS)
    assert cont.call_args.args[0] == 5
    # La consulta se recorta al período del envío del cliente.
    assert cass.call_args.args[1] == contenedor[4] and cass.call_args.args[2] == contenedor[5]
    fila = tabla.filas[0]
    assert fila[3:9] == (5, 4.0, 9.5, 85.0, 85.0, 2)
    assert fila[9] == "-32.9000, -68.0000" and fila[10] == "-33.4000, -68.0000"


# ------------------------------------------------------- ciclo completo

def reporte(estado="FACTURADO", **extra):
    base = dict(id_reporte=9, id_cliente=5, cliente="Viñedos", estado=estado, archivo=None,
                id_factura=None)
    base.update(extra)
    return base


def test_ciclo_solicitado_generado_facturado(tmp_path, monkeypatch):
    monkeypatch.setattr(cobrables, "CARPETA_REPORTES", tmp_path)
    tabla = exp.Tabla("T", ["A"], [("ñandú",)])
    with patch.object(repo, "crear_reporte", return_value=9) as crear, \
         patch.dict(cobrables.GENERADORES, {"PUNTUALIDAD": MagicMock(return_value=tabla)}), \
         patch.object(repo, "obtener_reporte", side_effect=[reporte("SOLICITADO"), reporte()]), \
         patch.object(repo, "marcar_generado") as generado, \
         patch.object(cobrables, "emitir_factura_reporte") as facturar:
        final = cobrables.solicitar_reporte(5, 8, "PUNTUALIDAD", "csv", PARAMS, hoy_=D2)
    assert crear.call_args.args == (5, 8, "PUNTUALIDAD", "CSV", PARAMS)
    ruta, filas, hash_ = generado.call_args.args[1:]
    assert ruta.endswith("9_PUNTUALIDAD.csv") and filas == 1 and len(hash_) == 64
    facturar.assert_called_once_with(9)
    assert final["estado"] == "FACTURADO"


def test_error_al_generar_no_factura(monkeypatch):
    with patch.object(repo, "crear_reporte", return_value=9), \
         patch.dict(cobrables.GENERADORES, {"OPERADORES": MagicMock(side_effect=RuntimeError("Neo4j caído"))}), \
         patch.object(repo, "marcar_error") as error, \
         patch.object(repo, "obtener_reporte", return_value=reporte("ERROR")), \
         patch.object(cobrables, "emitir_factura_reporte") as facturar:
        final = cobrables.solicitar_reporte(5, 8, "OPERADORES", "PDF", PARAMS, hoy_=D2)
    assert error.call_args.args[0] == 9 and "Neo4j caído" in str(error.call_args.args[1])
    facturar.assert_not_called()
    assert final["estado"] == "ERROR"


def test_si_falla_la_factura_queda_generado(tmp_path, monkeypatch):
    monkeypatch.setattr(cobrables, "CARPETA_REPORTES", tmp_path)
    with patch.object(repo, "crear_reporte", return_value=9), \
         patch.dict(cobrables.GENERADORES, {"INCIDENTES": MagicMock(return_value=exp.Tabla("T", ["A"]))}), \
         patch.object(repo, "obtener_reporte", side_effect=[reporte("SOLICITADO"), reporte("GENERADO")]), \
         patch.object(repo, "marcar_generado"), \
         patch.object(cobrables, "emitir_factura_reporte", side_effect=RuntimeError("caída")):
        assert cobrables.solicitar_reporte(5, 8, "INCIDENTES", "CSV", PARAMS, hoy_=D2)["estado"] == "GENERADO"


def test_formato_invalido_no_crea_reporte():
    with patch.object(repo, "crear_reporte") as crear, pytest.raises(ValueError, match="Formato"):
        cobrables.solicitar_reporte(5, 8, "INCIDENTES", "XLS", PARAMS, hoy_=D2)
    crear.assert_not_called()


def test_facturar_pendientes():
    with patch.object(repo, "listar_reportes", return_value=[{"id_reporte": 1}, {"id_reporte": 2}]) as listar, \
         patch.object(cobrables, "emitir_factura_reporte",
                      side_effect=[{"id_factura": 30}, RuntimeError("x")]):
        facturados, errores = cobrables.facturar_pendientes()
    assert listar.call_args.kwargs == {"estado": "GENERADO"}
    assert facturados == [{"id_factura": 30}] and errores == [(2, "x")]


def test_reporte_ajeno_no_existe_para_el_cliente():
    with patch.object(repo, "obtener_reporte", return_value=reporte(id_cliente=9)):
        assert cobrables.reporte_del_cliente(9, 5) is None
    with patch.object(repo, "obtener_reporte", return_value=reporte(id_cliente=5)):
        assert cobrables.reporte_del_cliente(9, 5)["id_reporte"] == 9


# ------------------------------------------------- factura del reporte

def crear_conexion_mock(cursor):
    conexion = MagicMock()
    conexion.__enter__.return_value = conexion
    conexion.cursor.return_value.__enter__.return_value = cursor
    return conexion


def test_factura_de_reporte_con_iva_movimiento_y_estado():
    cursor = MagicMock()
    cursor.rowcount = 1
    cursor.fetchone.side_effect = [(5, "GENERADO", Decimal("12000"), "PUNTUALIDAD", "ACTIVO", D2),
                                   None, ("ARS",), (77,)]
    with patch.object(fact_repo, "get_postgres_connection", return_value=crear_conexion_mock(cursor)):
        r = fact_repo.emitir_factura_reporte(9)
    assert (r["neto"], r["iva"], r["total"]) == (Decimal("12000.00"), Decimal("2520.00"), Decimal("14520.00"))
    sentencias = [(c.args[0], c.args[1] if len(c.args) > 1 else None) for c in cursor.execute.call_args_list]
    insert = next(p for s, p in sentencias if "INSERT INTO factura (" in s)
    assert insert[3] == "ARS" and insert[4] == 9 and insert[2] == Decimal("14520.00")
    assert any("'REPORTE'" in s and "factura_detalle" in s for s, _ in sentencias)
    mov = next(p for s, p in sentencias if "movimiento_cuenta_corriente" in s)
    assert mov[2] == Decimal("14520.00") and mov[4] == "77"
    assert any("SET estado = 'FACTURADO'" in s for s, _ in sentencias)


@pytest.mark.parametrize("fila, previa, error", [
    ((5, "SOLICITADO", Decimal("1"), "X", "ACTIVO", D2), None, ValueError),
    ((5, "FACTURADO", Decimal("1"), "X", "ACTIVO", D2), (3,), fact_repo.FacturaExistente),
    ((5, "GENERADO", Decimal("1"), "X", "INACTIVO", D2), None, ValueError),
])
def test_factura_de_reporte_rechazada(fila, previa, error):
    cursor = MagicMock()
    cursor.fetchone.side_effect = [fila, previa]
    with patch.object(fact_repo, "get_postgres_connection", return_value=crear_conexion_mock(cursor)):
        with pytest.raises(error):
            fact_repo.emitir_factura_reporte(9)
    assert not any("INSERT" in c.args[0] for c in cursor.execute.call_args_list)


# ---------------------------------------------- consultas por cliente

@pytest.mark.parametrize("funcion, args", [
    (repo.incidentes_cliente, (5, D1, D2)),
    (repo.contenedores_cliente, (5, D1, D2)),
    (repo.puntualidad_cliente, (5, D1, D2)),
    (repo.ids_envios_cliente, (5, D1, D2)),
])
def test_consultas_cobrables_filtran_por_cliente(funcion, args):
    with patch.object(repo, "_q", return_value=[]) as consulta:
        funcion(*args)
    sql, params = consulta.call_args.args
    assert "id_cliente = %s" in sql and params[0] == 5


def test_crear_reporte_copia_el_precio_vigente():
    cursor = MagicMock()
    cursor.fetchone.side_effect = [(Decimal("12000"),), (9,)]
    with patch.object(repo, "get_postgres_connection", return_value=crear_conexion_mock(cursor)):
        assert repo.crear_reporte(5, 8, "PUNTUALIDAD", "CSV", PARAMS) == 9
    params = cursor.execute.call_args.args[1]
    assert params[0:4] == (8, 5, "PUNTUALIDAD", "CSV") and params[5] == Decimal("12000")


def test_tipo_inactivo_no_se_puede_pedir():
    cursor = MagicMock()
    cursor.fetchone.return_value = None
    with patch.object(repo, "get_postgres_connection", return_value=crear_conexion_mock(cursor)):
        with pytest.raises(ValueError, match="inactivo"):
            repo.crear_reporte(5, 8, "PUNTUALIDAD", "CSV", PARAMS)


# --------------------------------------------------------- exportación

def test_csv_y_pdf_con_acentos_y_hash(tmp_path):
    tabla = exp.Tabla("Puntualidad de mis envíos", ["Envío", "Ruta", "Situación"],
                      [(5, "Mendoza → Santiago", "Tarde"), (7, "Asunción -> Córdoba", "A tiempo")],
                      "PostgreSQL", ["Nota con ñ"])
    ruta_csv, hash_csv = exp.exportar(tabla, "csv", tmp_path / "r", ["Cliente: Viñedos"])
    contenido = ruta_csv.read_text(encoding="utf-8-sig")
    assert "Asunción -> Córdoba" in contenido and "# Cliente: Viñedos" in contenido
    assert hash_csv == exp.hash_archivo(ruta_csv)
    ruta_pdf, hash_pdf = exp.exportar(tabla, "PDF", tmp_path / "r", ["Cliente: Viñedos"])
    assert ruta_pdf.read_bytes()[:5] == b"%PDF-" and len(hash_pdf) == 64
    with pytest.raises(ValueError):
        exp.exportar(tabla, "XLS", tmp_path / "r")


def test_meses_de_un_periodo():
    from app.repositories.lectura_iot_repository import meses_entre
    assert meses_entre(t("2026-11-20 00:00"), t("2027-01-02 00:00")) == ["2026-11", "2026-12", "2027-01"]


# ------------------------------------------------------ permisos y portal

def sesion(cli=None, nivel=5):
    return {"id_usuario": 8, "nivel_permisos": nivel, "id_cliente": cli,
            "id_proveedor": None, "id_operador": None, "nombre": "A", "apellido": "B"}


def con_sesion(s):
    pila = ExitStack()
    for modulo in (autenticacion, pantallas):
        pila.enter_context(patch.object(modulo, "obtener_sesion_actual", return_value=s))
    return pila


@pytest.mark.parametrize("funcion", [pantallas.generar_para_cliente_service,
                                     pantallas.facturar_reportes_pendientes_service,
                                     pantallas.precios_reportes_service])
def test_funciones_internas_de_reportes_bloqueadas_para_clientes(funcion, capsys):
    with con_sesion(sesion(cli=5)), patch("builtins.input", side_effect=AssertionError):
        assert funcion() is None
    assert "solo para usuarios internos" in capsys.readouterr().out


def test_portal_solicita_siempre_para_el_cliente_de_la_sesion():
    with con_sesion(sesion(cli=5, nivel=2)), \
         patch.object(pantallas, "pedir_solicitud", return_value=("PUNTUALIDAD", "CSV", PARAMS)), \
         patch.object(cobrables, "solicitar_reporte", return_value=reporte()) as solicitar, \
         patch.object(pantallas, "_resultado"), patch("builtins.input", return_value=""):
        pantallas.solicitar_mi_reporte_service()
    assert solicitar.call_args.args[:2] == (5, 8)


def test_portal_no_muestra_reportes_ajenos(capsys):
    with con_sesion(sesion(cli=5, nivel=2)), \
         patch.object(repo, "obtener_reporte", return_value=reporte(id_cliente=9)), \
         patch("builtins.input", side_effect=["9", ""]):
        pantallas.ver_mi_reporte_service()
    assert "No existe un reporte con ese número entre sus reportes" in capsys.readouterr().out


def test_mis_reportes_solo_para_usuarios_de_cliente(capsys):
    operador = {**sesion(), "id_operador": 3}
    with con_sesion(operador), patch.object(repo, "listar_reportes") as listar, \
         patch("builtins.input", return_value=""):
        pantallas.listar_mis_reportes_service()
    listar.assert_not_called()
    assert "usuarios de clientes" in capsys.readouterr().out


def test_mis_reportes_lista_solo_los_del_cliente():
    with con_sesion(sesion(cli=5, nivel=2)), patch.object(repo, "listar_reportes", return_value=[]) as listar, \
         patch("builtins.input", return_value=""):
        pantallas.listar_mis_reportes_service()
    listar.assert_called_once_with(5)


# ------------------------------------------------------ envío con países

def test_alta_de_envio_guarda_paises():
    from app.models.envio import Envio
    from app.repositories import envio_repository
    cursor = MagicMock()
    cursor.fetchone.return_value = (30,)
    with patch.object(envio_repository, "get_postgres_connection", return_value=crear_conexion_mock(cursor)):
        envio_repository.crear_envio(Envio(5, "Mendoza", "Santiago", "Pendiente", "Alta",
                                           pais_origen="Argentina", pais_destino="Chile"))
    sql, params = cursor.execute.call_args.args
    assert "pais_origen, pais_destino" in sql
    assert params[-2:] == ("Argentina", "Chile")


def test_mostrar_envio_indica_sin_dato(capsys):
    from app.services import envio_service
    fila = (2, 3, "C", "Buenos Aires", "Córdoba", "En tránsito", "Baja",
            datetime(2026, 10, 7, tzinfo=UTC), None, None, None)
    envio_service.mostrar_envio(fila)
    salida = capsys.readouterr().out
    assert "Buenos Aires (sin dato)" in salida and "Córdoba (sin dato)" in salida
