"""Fechas de tramos ingresadas como día: hora argentina (migración 017)."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from app.utils import formato
from app.utils.exportar_reportes import texto
from app.utils.validaciones_logistica import (
    dia_local,
    sale_despues_de_llegar,
    validar_fecha,
    validar_rango_fechas,
)

AR = ZoneInfo("America/Argentina/Buenos_Aires")


# ------------------------------------------------------------ parseo

def test_la_salida_es_el_inicio_del_dia_en_hora_argentina():
    salida = validar_fecha("2026-11-05", "La fecha de salida")
    assert salida == datetime(2026, 11, 5, 0, 0, 0, tzinfo=AR)
    assert salida.astimezone(timezone.utc) == datetime(2026, 11, 5, 3, 0, tzinfo=timezone.utc)
    assert dia_local(salida).isoformat() == "2026-11-05"


def test_la_llegada_estimada_vale_hasta_el_fin_del_dia():
    llegada = validar_fecha("2026-11-07", "La fecha estimada de llegada", fin_del_dia=True)
    assert llegada == datetime(2026, 11, 7, 23, 59, 59, tzinfo=AR)
    assert llegada.astimezone(timezone.utc) == datetime(2026, 11, 8, 2, 59, 59, tzinfo=timezone.utc)


@pytest.mark.parametrize("valor", ["05/11/2026", "2026-02-30", "", "mañana"])
def test_fecha_invalida(valor):
    with pytest.raises(ValueError, match="AAAA-MM-DD"):
        validar_fecha(valor, "La fecha de salida")


def test_salida_y_llegada_el_mismo_dia_es_un_rango_valido():
    salida = validar_fecha("2026-11-05", "s")
    llegada = validar_fecha("2026-11-05", "l", fin_del_dia=True)
    validar_rango_fechas(salida, llegada)            # no lanza


def test_una_entrega_el_dia_estimado_es_a_tiempo():
    from app.services.reportes_service import situacion
    llegada = validar_fecha("2026-11-07", "l", fin_del_dia=True)
    entrega = datetime(2026, 11, 7, 18, 30, tzinfo=AR)
    assert situacion("Entregado", llegada, entrega) == "A tiempo"
    assert situacion("En tránsito", llegada, None, ahora=datetime(2026, 11, 7, 22, 0, tzinfo=AR)) == "En curso"
    assert situacion("En tránsito", llegada, None, ahora=datetime(2026, 11, 8, 0, 1, tzinfo=AR)) == "Demorado"


# ------------------------------------------------------------ encadenado

def test_un_tramo_puede_salir_el_mismo_dia_en_que_llega_el_anterior():
    llegada_anterior = validar_fecha("2026-11-07", "l", fin_del_dia=True)
    assert sale_despues_de_llegar(validar_fecha("2026-11-07", "s"), llegada_anterior)
    assert sale_despues_de_llegar(validar_fecha("2026-11-08", "s"), llegada_anterior)
    assert not sale_despues_de_llegar(validar_fecha("2026-11-06", "s"), llegada_anterior)


def test_el_encadenado_compara_por_fecha_local_tambien_con_horas_reales():
    # Llegada con hora real a las 22:00 del 07/11 (01:00 UTC del 08/11).
    llegada = datetime(2026, 11, 8, 1, 0, tzinfo=timezone.utc)
    assert sale_despues_de_llegar(datetime(2026, 11, 7, 23, 0, tzinfo=AR), llegada)
    assert not sale_despues_de_llegar(datetime(2026, 11, 6, 23, 0, tzinfo=AR), llegada)


# ------------------------------------------------------------ formato

def test_se_muestra_solo_la_fecha_cuando_se_cargo_como_dia():
    assert formato.fecha_tramo(validar_fecha("2026-11-05", "s")) == "05/11/2026"
    assert formato.fecha_tramo(validar_fecha("2026-11-07", "l", fin_del_dia=True)) == "07/11/2026"
    # Mismos instantes vistos desde UTC (como los devuelve otra sesión).
    assert formato.fecha_tramo(datetime(2026, 11, 5, 3, 0, tzinfo=timezone.utc)) == "05/11/2026"
    assert formato.fecha_tramo(datetime(2026, 11, 8, 2, 59, 59, tzinfo=timezone.utc)) == "07/11/2026"


def test_las_horas_reales_se_siguen_mostrando():
    assert formato.fecha_tramo(datetime(2026, 8, 5, 8, 0, tzinfo=AR)) == "05/08/2026 08:00"
    # El error viejo (00:00 UTC) ya no se confunde con un día: se ve con su hora.
    assert formato.fecha_tramo(datetime(2026, 11, 5, 0, 0, tzinfo=timezone.utc)) == "04/11/2026 21:00"
    assert formato.fecha_tramo(None) == "-"


def test_formato_acepta_fechas_de_neo4j_y_texto_iso():
    class FechaNeo4j:
        def to_native(self):
            return datetime(2026, 11, 7, 23, 59, 59, tzinfo=AR)
    assert formato.fecha_tramo(FechaNeo4j()) == "07/11/2026"
    assert formato.fecha_tramo("2026-11-05T00:00:00-03:00") == "05/11/2026"


def test_los_reportes_muestran_la_llegada_estimada_como_fecha():
    assert texto(validar_fecha("2026-11-07", "l", fin_del_dia=True)) == "07/11/2026"
    assert texto(datetime(2026, 8, 5, 11, 0, tzinfo=timezone.utc)) == "05/08/2026 08:00"
    assert texto(datetime(2026, 8, 5, 8, 0)) == "05/08/2026 08:00"        # sin zona: tal cual


# ------------------------------------------------------------ migración 017

def test_la_migracion_017_solo_toca_tramos_a_las_00_utc_exactas():
    sql = (Path(__file__).resolve().parents[1] / "scripts" / "migrations"
           / "017_fechas_tramos_hora_argentina.sql").read_text(encoding="utf-8")
    assert "BEGIN;" in sql and "COMMIT;" in sql
    assert "(fecha_salida AT TIME ZONE 'UTC')::time = TIME '00:00:00'" in sql
    assert "(fecha_estimada_llegada AT TIME ZONE 'UTC')::time = TIME '00:00:00'" in sql
    assert "TIME '23:59:59'" in sql and "America/Argentina/Buenos_Aires" in sql


def test_criterio_de_la_017_conserva_el_dia_ingresado():
    # Lo que guardaba la versión anterior para salida 05/11 y llegada 07/11.
    viejo_salida = datetime(2026, 11, 5, tzinfo=timezone.utc)
    viejo_llegada = datetime(2026, 11, 7, tzinfo=timezone.utc)
    nuevo_salida = datetime.combine(viejo_salida.date(), datetime.min.time(), AR)
    nuevo_llegada = datetime.combine(viejo_llegada.date(), datetime.min.time(), AR) \
        + timedelta(hours=23, minutes=59, seconds=59)
    assert nuevo_salida == validar_fecha("2026-11-05", "s")
    assert nuevo_llegada == validar_fecha("2026-11-07", "l", fin_del_dia=True)
