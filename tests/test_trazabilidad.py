from datetime import datetime, timezone

import pytest

from app.utils.validaciones_trazabilidad import (
    normalizar_nombre_grafo,
    parsear_fecha_hora,
    validar_coordenada,
    validar_numero_opcional,
    validar_evento_permitido,
    estado_nuevo_por_evento,
    ultimos_meses,
    muestrear,
    fusionar_recorrido
)

AHORA = datetime(2026, 10, 13, 15, 0, tzinfo=timezone.utc)


def test_normalizar_nombre_grafo_unifica_variantes():
    assert normalizar_nombre_grafo("Montevideo") == "montevideo"
    assert normalizar_nombre_grafo("MONTEVIDEO") == "montevideo"
    assert normalizar_nombre_grafo("  Montevideo  ") == "montevideo"
    assert normalizar_nombre_grafo("Buenos   Aires") == "buenos aires"
    assert normalizar_nombre_grafo("Panamá") == "panama"
    assert normalizar_nombre_grafo(None) == ""


def test_fecha_vacia_devuelve_ahora():
    assert parsear_fecha_hora("", ahora=AHORA) == AHORA


def test_fecha_se_interpreta_en_hora_argentina():
    fecha = parsear_fecha_hora("2026-10-10 09:30", ahora=AHORA)
    assert fecha == datetime(2026, 10, 10, 12, 30, tzinfo=timezone.utc)


def test_fecha_futura_o_invalida_se_rechaza():
    with pytest.raises(ValueError):
        parsear_fecha_hora("2026-12-01 10:00", ahora=AHORA)

    with pytest.raises(ValueError):
        parsear_fecha_hora("10/10/2026", ahora=AHORA)


def test_validar_coordenada():
    assert validar_coordenada("", "Lat", -90, 90) is None
    assert validar_coordenada("-34,6", "Lat", -90, 90) == -34.6

    with pytest.raises(ValueError):
        validar_coordenada("120", "Lat", -90, 90)

    with pytest.raises(ValueError):
        validar_coordenada("abc", "Lat", -90, 90)


def test_validar_numero_opcional():
    assert validar_numero_opcional("", "Horas") is None
    assert validar_numero_opcional("6,5", "Horas") == 6.5

    with pytest.raises(ValueError):
        validar_numero_opcional("-1", "Horas")


@pytest.mark.parametrize("estado", ["Cancelado", "Entregado"])
def test_envio_cerrado_no_admite_eventos(estado):
    with pytest.raises(ValueError):
        validar_evento_permitido(estado, "EN_TRANSITO", set())


def test_no_se_repite_entregado():
    with pytest.raises(ValueError):
        validar_evento_permitido(
            "En tránsito", "ENTREGADO", {"ENTREGADO"}
        )


def test_entregado_sin_transito_solo_advierte():
    avisos = validar_evento_permitido("Pendiente", "ENTREGADO", set())
    assert len(avisos) == 1


def test_entregado_con_transito_no_advierte():
    avisos = validar_evento_permitido(
        "En tránsito", "ENTREGADO", {"EN_TRANSITO"}
    )
    assert avisos == []


def test_estado_nuevo_por_evento():
    # Iniciar la carga no implica que el envío ya esté en tránsito.
    assert estado_nuevo_por_evento("CARGA_INICIADA", "Pendiente") is None

    # El envío pasa a En tránsito cuando comienza el transporte.
    assert estado_nuevo_por_evento("EN_TRANSITO", "Pendiente") == "En tránsito"

    # Si ya estaba en tránsito, no necesita cambiar de estado.
    assert estado_nuevo_por_evento("EN_TRANSITO", "En tránsito") is None

    # La entrega finaliza el envío.
    assert estado_nuevo_por_evento("ENTREGADO", "En tránsito") == "Entregado"


def test_ultimos_meses_cruza_el_anio():
    assert ultimos_meses(3, datetime(2026, 1, 15, tzinfo=timezone.utc)) == [
        "2025-11", "2025-12", "2026-01"
    ]
    assert ultimos_meses(1, AHORA) == ["2026-10"]


def test_muestrear_conserva_extremos():
    datos = list(range(100))
    muestra = muestrear(datos, 10)
    assert len(muestra) <= 10
    assert muestra[0] == 0 and muestra[-1] == 99
    assert muestrear([1, 2, 3], 10) == [1, 2, 3]


def test_fusionar_recorrido_ordena_eventos_y_gps():
    eventos = [{
        "envio_id": 1,
        "tipo": "EN_TRANSITO",
        "fecha_hora": datetime(2026, 10, 2, tzinfo=timezone.utc),
        "ubicacion": {"nombre": "Montevideo"}
    }]
    puntos = [
        {
            "fecha_hora": datetime(2026, 10, 3),  # Cassandra: sin zona
            "sensor_id": 5, "lat": -34.6, "lon": -58.4
        },
        {
            "fecha_hora": datetime(2026, 10, 1),
            "sensor_id": 5, "lat": -34.7, "lon": -58.5
        }
    ]

    linea = fusionar_recorrido(eventos, puntos)

    assert [i["origen"] for i in linea] == ["GPS", "EVENTO", "GPS"]
