from datetime import datetime, timezone
from unittest.mock import patch

import pytest

import ejecutar_procesos
from app.services import procesos_periodicos_service as procesos


def resultado_sensores(errores=None):
    return {
        "sensores_activos": 1,
        "al_dia": 0,
        "sin_lecturas": [],
        "atrasados": [],
        "alertas_procesadas": 1,
        "errores": errores or [],
    }


def resultado_predicciones(errores=0):
    return {
        "total": 1,
        "guardadas": 1 - errores,
        "riesgos_altos": 0,
        "errores": errores,
    }


def test_ejecutar_solo_sensores_no_llama_predicciones():
    sensores = resultado_sensores()

    with patch.object(
        procesos, "ejecutar_revision_sensores", return_value=sensores
    ) as revisar, patch.object(
        procesos, "ejecutar_predicciones_diarias"
    ) as predicciones:
        resultado = procesos.ejecutar_todos_los_procesos(
            horas_sensores=24,
            procesos=("sensores",),
        )

    revisar.assert_called_once_with(horas=24)
    predicciones.assert_not_called()
    assert resultado["sensores"] == sensores
    assert resultado["predicciones"] is None
    assert resultado["errores"] == {}


def test_ejecutar_solo_predicciones_no_llama_sensores():
    predicciones_resultado = resultado_predicciones()

    with patch.object(
        procesos,
        "ejecutar_predicciones_diarias",
        return_value=predicciones_resultado,
    ) as actualizar, patch.object(
        procesos, "ejecutar_revision_sensores"
    ) as revisar:
        resultado = procesos.ejecutar_todos_los_procesos(
            procesos=("predicciones",),
        )

    actualizar.assert_called_once_with()
    revisar.assert_not_called()
    assert resultado["predicciones"] == predicciones_resultado
    assert resultado["sensores"] is None


def test_ejecutar_todos_intenta_el_segundo_trabajo_si_falla_el_primero():
    sensores = resultado_sensores()

    with patch.object(
        procesos,
        "ejecutar_predicciones_diarias",
        side_effect=RuntimeError("Mongo no disponible"),
    ), patch.object(
        procesos,
        "ejecutar_revision_sensores",
        return_value=sensores,
    ) as revisar:
        resultado = procesos.ejecutar_todos_los_procesos()

    # Sin horas explícitas, la revisión usa el umbral de la regla de alerta.
    revisar.assert_called_once_with(horas=None)
    assert resultado["errores"] == {
        "predicciones": "Mongo no disponible"
    }
    assert resultado["sensores"] == sensores


@pytest.mark.parametrize(
    "ahora,dia_esperado",
    [
        # 01:00 UTC del día 27 todavía es 22:00 del día 26 en Argentina.
        (datetime(2026, 10, 27, 1, tzinfo=timezone.utc), "2026-10-26"),
        # 03:30 UTC ya es 00:30 del día 27 en Argentina.
        (datetime(2026, 10, 27, 3, 30, tzinfo=timezone.utc), "2026-10-27"),
    ],
)
def test_revision_sensores_usa_dia_argentino_y_reutiliza_clave(
    ahora,
    dia_esperado,
):
    sensor = (9, 4, "CONTENEDOR-4", "Temperatura", None, None, "Activo")

    with patch.object(
        procesos, "listar_sensores", return_value=[sensor]
    ), patch.object(
        procesos, "consultar_ultima_lectura_db", return_value=None
    ), patch(
        "app.services.incidentes_service.buscar_envios_activos_de_contenedor",
        return_value=[],
    ), patch.object(procesos, "emitir_alerta") as registrar:
        primera = procesos.detectar_sensores_inactivos_automatico(
            ahora=ahora
        )
        segunda = procesos.detectar_sensores_inactivos_automatico(
            ahora=ahora
        )

    claves = [
        llamada.kwargs["clave_deteccion"]
        for llamada in registrar.call_args_list
    ]
    assert claves == [
        f"9:Sensor sin lecturas registradas:{dia_esperado}",
        f"9:Sensor sin lecturas registradas:{dia_esperado}",
    ]
    assert primera["alertas_procesadas"] == 1
    assert segunda["alertas_procesadas"] == 1


def test_revision_sensores_acumula_error_individual():
    sensor = (9, 4, "CONTENEDOR-4", "Temperatura", None, None, "Activo")

    with patch.object(
        procesos, "listar_sensores", return_value=[sensor]
    ), patch.object(
        procesos,
        "consultar_ultima_lectura_db",
        side_effect=RuntimeError("Cassandra no disponible"),
    ), patch(
        "app.services.incidentes_service.buscar_envios_activos_de_contenedor",
        return_value=[],
    ), patch.object(procesos, "emitir_alerta") as registrar:
        resultado = procesos.detectar_sensores_inactivos_automatico()

    assert resultado["errores"] == [{
        "sensor_id": 9,
        "error": "Cassandra no disponible",
    }]
    registrar.assert_not_called()


@pytest.mark.parametrize(
    "resultado,esperado",
    [
        ({"errores": {"sensores": "fallo general"}}, True),
        ({"predicciones": {"errores": 1}}, True),
        ({"sensores": {"errores": [{"sensor_id": 4}]}}, True),
        ({"predicciones": {"errores": 0}, "sensores": {"errores": []}}, False),
    ],
)
def test_hay_errores_incluye_fallos_generales_e_individuales(
    resultado,
    esperado,
):
    assert ejecutar_procesos.hay_errores(resultado) is esperado


def test_lanzador_devuelve_codigo_distinto_de_cero_por_error_individual():
    resultado = {
        "fecha_ejecucion": datetime.now(timezone.utc),
        "predicciones": resultado_predicciones(errores=1),
        "sensores": None,
        "errores": {},
    }

    with patch.object(
        ejecutar_procesos,
        "ejecutar_todos_los_procesos",
        return_value=resultado,
    ) as ejecutar:
        codigo = ejecutar_procesos.main(["--job", "predicciones"])

    assert codigo == 1
    assert ejecutar.call_args.kwargs["procesos"] == ("predicciones",)


def test_lanzador_devuelve_cero_si_no_hay_errores():
    resultado = {
        "fecha_ejecucion": datetime.now(timezone.utc),
        "predicciones": resultado_predicciones(),
        "sensores": resultado_sensores(),
        "errores": {},
    }

    with patch.object(
        ejecutar_procesos,
        "ejecutar_todos_los_procesos",
        return_value=resultado,
    ) as ejecutar:
        codigo = ejecutar_procesos.main(["--job", "todos"])

    assert codigo == 0
    assert ejecutar.call_args.kwargs["procesos"] == (
        "predicciones",
        "sensores",
    )


def test_guardar_prediccion_actualiza_un_unico_registro_diario():
    from app.repositories import predicciones_repository as repo

    prediccion = {
        "envio_id": 23,
        "fecha_calculo": datetime(2026, 10, 26, 12, tzinfo=timezone.utc),
        "nivel_riesgo": "MEDIO",
    }
    mock_db = patch(
        "app.repositories.predicciones_repository.get_mongo_database"
    )

    with mock_db as obtener_db:
        resultado_db = {"_id": "prediccion-diaria-23"}
        mocks = obtener_db.return_value
        mocks.__getitem__.return_value.find_one_and_update.return_value = resultado_db

        resultado = repo.guardar_prediccion(prediccion)

    assert resultado == "prediccion-diaria-23"
    llamada = mocks.__getitem__.return_value.find_one_and_update.call_args
    assert llamada.args[0] == {
        "envio_id": 23,
        "dia_calculo": "2026-10-26",
    }
    assert llamada.args[1]["$set"]["dia_calculo"] == "2026-10-26"
    assert llamada.kwargs["upsert"] is True


def test_dia_prediccion_se_calcula_en_hora_argentina():
    from app.repositories import predicciones_repository as repo

    prediccion = {
        "envio_id": 24,
        "fecha_calculo": datetime(2026, 10, 27, 1, tzinfo=timezone.utc),
        "nivel_riesgo": "BAJO",
    }
    mock_db = patch(
        "app.repositories.predicciones_repository.get_mongo_database"
    )

    with mock_db as mock_obtener_db:
        coleccion = mock_obtener_db.return_value.__getitem__.return_value
        coleccion.find_one_and_update.return_value = {"_id": "prediccion-24"}

        repo.guardar_prediccion(prediccion)

    filtro = coleccion.find_one_and_update.call_args.args[0]
    assert filtro["dia_calculo"] == "2026-10-26"


def test_guardar_prediccion_rechaza_fecha_sin_zona_horaria():
    from app.repositories import predicciones_repository as repo

    with pytest.raises(ValueError, match="zona horaria"):
        repo.guardar_prediccion({
            "envio_id": 23,
            "fecha_calculo": datetime(2026, 10, 26, 12),
        })
