
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from app.services.predicciones_service import (
    calcular_riesgo,
    clasificar_riesgo,
    actualizar_predicciones_activas,
)


AHORA = datetime(2026, 10, 15, 15, 0, tzinfo=timezone.utc)


def datos_envio(
    estado="En tránsito",
    prioridad="Media",
    tramos=None,
    incidentes=None
):
    return {
        "envio_id": 1,
        "cliente": "Cliente de prueba",
        "estado": estado,
        "prioridad": prioridad,
        "fecha_creacion": AHORA - timedelta(days=2),
        "tramos": tramos if tramos is not None else [],
        "incidentes": incidentes if incidentes is not None else [],
    }


def tramo_con_llegada(horas_desde_ahora):
    return (
        AHORA - timedelta(days=1),
        AHORA + timedelta(hours=horas_desde_ahora)
    )


def test_riesgo_bajo():
    resultado = calcular_riesgo(
        datos_envio(tramos=[tramo_con_llegada(72)]),
        AHORA
    )
    assert resultado["nivel_riesgo"] == "BAJO"
    assert resultado["puntaje_riesgo"] == 0


def test_llegada_estimada_vencida():
    resultado = calcular_riesgo(
        datos_envio(tramos=[tramo_con_llegada(-5)]),
        AHORA
    )
    assert resultado["puntaje_demora"] == 30


def test_demora_mayor_a_24_horas():
    resultado = calcular_riesgo(
        datos_envio(tramos=[tramo_con_llegada(-30)]),
        AHORA
    )
    assert resultado["puntaje_demora"] == 45


def test_demora_mayor_a_48_horas():
    resultado = calcular_riesgo(
        datos_envio(tramos=[tramo_con_llegada(-60)]),
        AHORA
    )
    assert resultado["puntaje_demora"] == 60


def test_incidente_critico():
    resultado = calcular_riesgo(
        datos_envio(
            incidentes=[("Crítica", "Abierto")]
        ),
        AHORA
    )
    assert resultado["puntaje_operativo"] == 35


def test_incidente_cerrado_no_suma_riesgo():
    resultado = calcular_riesgo(
        datos_envio(
            incidentes=[("Alta", "Cerrado")]
        ),
        AHORA
    )
    assert resultado["puntaje_operativo"] == 0


def test_varios_incidentes_limitan_puntaje_operativo():
    resultado = calcular_riesgo(
        datos_envio(
            incidentes=[
                ("Crítica", "Abierto"),
                ("Crítica", "Abierto"),
                ("Alta", "Abierto"),
            ]
        ),
        AHORA
    )
    assert resultado["puntaje_operativo"] == 60


def test_prioridad_alta_suma_riesgo():
    resultado = calcular_riesgo(
        datos_envio(prioridad="Alta"),
        AHORA
    )
    assert resultado["puntaje_operativo"] == 10


def test_riesgo_alto_por_demora_e_incidentes():
    resultado = calcular_riesgo(
        datos_envio(
            tramos=[tramo_con_llegada(-60)],
            incidentes=[("Alta", "Abierto")]
        ),
        AHORA
    )
    assert resultado["nivel_riesgo"] == "ALTO"
    assert resultado["puntaje_riesgo"] == 85


def test_puntaje_no_supera_100():
    resultado = calcular_riesgo(
        datos_envio(
            prioridad="Alta",
            tramos=[tramo_con_llegada(-60)],
            incidentes=[
                ("Crítica", "Abierto"),
                ("Crítica", "Abierto"),
                ("Crítica", "Abierto"),
            ]
        ),
        AHORA
    )
    assert resultado["puntaje_riesgo"] == 100


def test_envio_finalizado_no_tiene_riesgo_activo():
    resultado = calcular_riesgo(
        datos_envio(
            estado="Entregado",
            tramos=[tramo_con_llegada(-60)],
            incidentes=[("Alta", "Abierto")]
        ),
        AHORA
    )
    assert resultado["puntaje_riesgo"] == 0


def test_riesgo_climatico_no_se_inventa():
    resultado = calcular_riesgo(datos_envio(), AHORA)
    assert resultado["riesgo_climatico"] == "NO EVALUADO"


def test_sin_tramos_se_informa_limitacion():
    resultado = calcular_riesgo(datos_envio(), AHORA)
    assert any(
        "Sin tramos" in motivo
        for motivo in resultado["motivos"]
    )


def test_envio_inexistente():
    with pytest.raises(ValueError):
        calcular_riesgo(None, AHORA)


def test_clasificacion_riesgo():
    assert clasificar_riesgo(0) == "BAJO"
    assert clasificar_riesgo(34) == "BAJO"
    assert clasificar_riesgo(35) == "MEDIO"
    assert clasificar_riesgo(69) == "MEDIO"
    assert clasificar_riesgo(70) == "ALTO"


def test_sin_tramos_informa_datos_insuficientes():
    resultado = calcular_riesgo(datos_envio(), AHORA)
    assert resultado["nivel_riesgo"] == "INFORMACIÓN INSUFICIENTE"
    assert resultado["datos_suficientes"] is False


def test_tramos_sin_fecha_estimada():
    resultado = calcular_riesgo(
        datos_envio(
            tramos=[
                (AHORA - timedelta(days=1), None)
            ]
        ),
        AHORA
    )
    assert resultado["nivel_riesgo"] == "INFORMACIÓN INSUFICIENTE"
    assert resultado["datos_suficientes"] is False


def test_con_fecha_estimada_permite_riesgo_bajo():
    resultado = calcular_riesgo(
        datos_envio(
            tramos=[tramo_con_llegada(72)]
        ),
        AHORA
    )
    assert resultado["nivel_riesgo"] == "BAJO"
    assert resultado["datos_suficientes"] is True


def test_incidentes_con_datos_incompletos():
    resultado = calcular_riesgo(
        datos_envio(
            incidentes=[
                ("Alta", "Abierto"),
                ("Media", "Abierto"),
            ]
        ),
        AHORA
    )
    assert resultado["nivel_riesgo"] == "MEDIO"
    assert resultado["puntaje_operativo"] == 40
    assert resultado["datos_suficientes"] is False


def test_envio_finalizado_no_requiere_datos_de_demora():
    resultado = calcular_riesgo(
        datos_envio(estado="Entregado"),
        AHORA
    )
    assert resultado["nivel_riesgo"] == "BAJO"
    assert resultado["puntaje_riesgo"] == 0
    assert resultado["datos_suficientes"] is True


def test_riesgo_operativo_parcial_visible():
    resultado = calcular_riesgo(
        datos_envio(
            incidentes=[("Alta", "Abierto")]
        ),
        AHORA
    )
    assert resultado["puntaje_operativo"] == 25
    assert resultado["nivel_riesgo_operativo"] == "BAJO"
    assert resultado["nivel_riesgo"] == "INFORMACIÓN INSUFICIENTE"
    assert resultado["evaluacion_parcial"] is True


def test_incidente_en_proceso_cuenta_como_abierto():
    resultado = calcular_riesgo(
        datos_envio(
            incidentes=[("Media", "En proceso")]
        ),
        AHORA
    )
    assert resultado["puntaje_operativo"] == 15
    assert resultado["incidentes_abiertos"] == 1


def test_prioridad_media_no_suma_riesgo():
    resultado = calcular_riesgo(
        datos_envio(
            prioridad="Media",
            tramos=[tramo_con_llegada(72)]
        ),
        AHORA
    )
    assert resultado["puntaje_operativo"] == 0


@patch(
    "app.services.predicciones_service.guardar_prediccion"
)
@patch(
    "app.services.predicciones_service.obtener_datos_riesgo"
)
@patch(
    "app.services.predicciones_service.listar_envios_analisis"
)
def test_actualizacion_masiva_sin_interaccion(
    mock_listar,
    mock_obtener,
    mock_guardar
):
    mock_listar.return_value = [
        (1, "Cliente", "A", "B", "En tránsito"),
        (2, "Cliente", "A", "B", "Entregado"),
    ]

    mock_obtener.return_value = datos_envio(
        tramos=[tramo_con_llegada(72)]
    )

    resumen = actualizar_predicciones_activas()

    assert resumen["total"] == 1
    assert resumen["guardadas"] == 1
    assert resumen["errores"] == 0
    assert mock_obtener.call_count == 1
    assert mock_guardar.call_count == 1


@patch(
    "app.services.predicciones_service.guardar_prediccion"
)
@patch(
    "app.services.predicciones_service.obtener_datos_riesgo"
)
@patch(
    "app.services.predicciones_service.listar_envios_analisis"
)
def test_actualizacion_masiva_registra_errores(
    mock_listar,
    mock_obtener,
    mock_guardar
):
    mock_listar.return_value = [
        (1, "Cliente", "A", "B", "En tránsito"),
    ]

    mock_obtener.side_effect = RuntimeError(
        "Error de prueba"
    )

    resumen = actualizar_predicciones_activas()

    assert resumen["total"] == 1
    assert resumen["guardadas"] == 0
    assert resumen["errores"] == 1
    assert resumen["resultados"][0]["guardada"] is False
    mock_guardar.assert_not_called()
