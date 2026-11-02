
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.services import incidentes_service
from app.services.deteccion_sensores import REGLAS_POR_DEFECTO
from app.repositories import incidente_repository, alerta_repository


@pytest.fixture
def lectura_anomala():
    return SimpleNamespace(
        id_lectura="lectura-test-001",
        fecha_hora=datetime.now(timezone.utc),
        temperatura=16.0,
        humedad=None,
        vibracion=None,
        bateria=10.0,
    )


def test_detectar_dos_anomalias_en_una_lectura(lectura_anomala):
    resultados = incidentes_service.detectar_anomalias(lectura_anomala, REGLAS_POR_DEFECTO)

    assert len(resultados) == 2
    assert resultados[0][0] == "Temperatura alta"
    assert resultados[0][1] == "Alta"
    assert resultados[1][0] == "Batería baja"
    assert resultados[1][1] == "Media"


def test_lectura_normal_no_genera_anomalias():
    lectura = SimpleNamespace(
        temperatura=5.0,
        humedad=60.0,
        vibracion=5.0,
        bateria=90.0,
    )

    resultados = incidentes_service.detectar_anomalias(lectura, REGLAS_POR_DEFECTO)

    assert resultados == []


def test_valores_iguales_al_limite_no_generan_anomalias():
    lectura = SimpleNamespace(
        temperatura=8.0,
        humedad=80.0,
        vibracion=15.0,
        bateria=20.0,
    )

    resultados = incidentes_service.detectar_anomalias(lectura, REGLAS_POR_DEFECTO)

    assert resultados == []


def test_valores_invalidos_se_ignoran():
    lectura = SimpleNamespace(
        temperatura=float("nan"),
        humedad="no disponible",
        vibracion=float("inf"),
        bateria=None,
    )

    resultados = incidentes_service.detectar_anomalias(lectura, REGLAS_POR_DEFECTO)

    assert resultados == []


def test_incidente_iot_se_crea_con_marca_unica():
    conexion = MagicMock()

    cursor = conexion.__enter__.return_value.cursor.return_value.__enter__.return_value

    cursor.fetchone.side_effect = [
        None,
        (10,),
    ]

    with patch.object(
        incidente_repository,
        "get_postgres_connection",
        return_value=conexion,
    ):
        id_incidente, creado = (
            incidente_repository.obtener_o_crear_incidente_iot(
                id_envio=3,
                id_sensor=1,
                id_lectura="lectura-test-001",
                tipo="Temperatura alta",
                severidad="Alta",
                descripcion="Temperatura alta de prueba",
            )
        )

    assert id_incidente == 10
    assert creado is True

    consultas = [
        llamada.args[0]
        for llamada in cursor.execute.call_args_list
    ]

    assert any("INSERT INTO incidente" in sql for sql in consultas)

    parametros_insert = [
        llamada.args[1]
        for llamada in cursor.execute.call_args_list
        if "INSERT INTO incidente" in llamada.args[0]
    ][0]

    assert (
        "[iot:1:lectura-test-001:Temperatura alta]"
        in parametros_insert[3]
    )


def test_incidente_iot_existente_se_reutiliza():
    conexion = MagicMock()
    cursor = conexion.__enter__.return_value.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = (10,)

    with patch.object(
        incidente_repository,
        "get_postgres_connection",
        return_value=conexion,
    ):
        id_incidente, creado = (
            incidente_repository.obtener_o_crear_incidente_iot(
                id_envio=3,
                id_sensor=1,
                id_lectura="lectura-test-001",
                tipo="Temperatura alta",
                severidad="Alta",
                descripcion="Temperatura alta de prueba",
            )
        )

    assert id_incidente == 10
    assert creado is False

    consultas = [
        llamada.args[0]
        for llamada in cursor.execute.call_args_list
    ]

    assert not any("INSERT INTO incidente" in sql for sql in consultas)


def test_cada_tipo_de_anomalia_tiene_clave_diferente():
    conexion = MagicMock()
    cursor = conexion.__enter__.return_value.cursor.return_value.__enter__.return_value
    cursor.fetchone.side_effect = [
        None, (10,),
        None, (11,),
    ]

    with patch.object(
        incidente_repository,
        "get_postgres_connection",
        return_value=conexion,
    ):
        temperatura = incidente_repository.obtener_o_crear_incidente_iot(
            3, 1, "lectura-test-001",
            "Temperatura alta", "Alta", "Temperatura elevada",
        )

        bateria = incidente_repository.obtener_o_crear_incidente_iot(
            3, 1, "lectura-test-001",
            "Batería baja", "Media", "Batería insuficiente",
        )

    assert temperatura == (10, True)
    assert bateria == (11, True)

    inserciones = [
        llamada.args[1][3]
        for llamada in cursor.execute.call_args_list
        if "INSERT INTO incidente" in llamada.args[0]
    ]

    assert len(inserciones) == 2
    assert "[iot:1:lectura-test-001:Temperatura alta]" in inserciones[0]
    assert "[iot:1:lectura-test-001:Batería baja]" in inserciones[1]


def test_alerta_mongodb_usa_clave_de_deteccion():
    coleccion = MagicMock()
    coleccion.find_one.return_value = {
        "_id": "alerta-test-001",
        "clave_deteccion": "1:lectura-test-001:Temperatura alta",
    }

    with patch.object(
        alerta_repository,
        "coleccion_alertas",
        return_value=coleccion,
    ), patch.object(alerta_repository, "ultimo_evento_envio", return_value=None):
        alerta = alerta_repository.registrar_alerta(
            sensor_id=1,
            contenedor_id=2,
            tipo="Temperatura alta",
            severidad="Alta",
            descripcion="Temperatura elevada",
            lectura_id="lectura-test-001",
            envio_id=3,
        )

    assert alerta["_id"] == "alerta-test-001"

    argumentos = coleccion.update_one.call_args
    filtro = argumentos.args[0]
    actualizacion = argumentos.args[1]

    assert filtro["clave_deteccion"] == (
        "1:lectura-test-001:Temperatura alta"
    )
    assert "$setOnInsert" in actualizacion
    assert argumentos.kwargs["upsert"] is True


def test_alertas_de_tipos_diferentes_tienen_claves_distintas():
    coleccion = MagicMock()
    coleccion.find_one.return_value = {"_id": "alerta-test"}

    with patch.object(
        alerta_repository,
        "coleccion_alertas",
        return_value=coleccion,
    ), patch.object(alerta_repository, "ultimo_evento_envio", return_value=None):
        alerta_repository.registrar_alerta(
            1, 2, "Temperatura alta", "Alta",
            "Temperatura elevada", "lectura-test-001", 3,
        )
        alerta_repository.registrar_alerta(
            1, 2, "Batería baja", "Media",
            "Batería insuficiente", "lectura-test-001", 3,
        )

    llamadas = coleccion.update_one.call_args_list

    clave_temperatura = llamadas[0].args[0]["clave_deteccion"]
    clave_bateria = llamadas[1].args[0]["clave_deteccion"]

    assert clave_temperatura != clave_bateria


def test_alerta_existente_no_se_reinicia():
    coleccion = MagicMock()
    coleccion.find_one.return_value = {
        "_id": "alerta-test-001",
        "estado": "Atendida",
        "incidente_id": 10,
    }
    coleccion.update_one.return_value.upserted_id = None

    with patch.object(
        alerta_repository,
        "coleccion_alertas",
        return_value=coleccion,
    ), patch.object(alerta_repository, "ultimo_evento_envio", return_value=None):
        resultado = alerta_repository.registrar_alerta(
            1, 2, "Temperatura alta", "Alta",
            "Temperatura elevada", "lectura-test-001", 3,
        )

    assert resultado["estado"] == "Atendida"
    assert resultado["incidente_id"] == 10

    actualizacion = coleccion.update_one.call_args.args[1]
    assert "$setOnInsert" in actualizacion
    assert "$set" not in actualizacion
    assert resultado["nueva"] is False


def test_alerta_se_vincula_a_incidente():
    coleccion = MagicMock()
    coleccion.update_one.return_value.matched_count = 1

    with patch.object(
        alerta_repository,
        "coleccion_alertas",
        return_value=coleccion,
    ), patch.object(alerta_repository, "ultimo_evento_envio", return_value=None):
        resultado = alerta_repository.vincular_incidente_alerta(
            "507f1f77bcf86cd799439011",
            10,
        )

    assert resultado is None

    actualizacion = coleccion.update_one.call_args.args[1]
    assert actualizacion == {"$set": {"incidente_id": 10}}


def test_vincular_alerta_inexistente_produce_error():
    coleccion = MagicMock()
    coleccion.update_one.return_value.matched_count = 0

    with patch.object(
        alerta_repository,
        "coleccion_alertas",
        return_value=coleccion,
    ), patch.object(alerta_repository, "ultimo_evento_envio", return_value=None):
        with pytest.raises(RuntimeError):
            alerta_repository.vincular_incidente_alerta(
                "507f1f77bcf86cd799439011",
                10,
            )


def test_incidente_correcto_se_reutiliza():
    alerta = {
        "_id": "507f1f77bcf86cd799439011",
        "incidente_id": 10,
    }

    incidente = (
        10,
        3,
        "Temperatura alta",
        datetime.now(timezone.utc),
        "Alta",
        "Abierto",
        "Temperatura elevada | Sensor 1 "
        "[iot:1:lectura-test-001:Temperatura alta]",
    )

    with patch.object(
        incidentes_service,
        "buscar_incidente",
        return_value=incidente,
    ), patch.object(
        incidentes_service,
        "obtener_o_crear_incidente_iot",
    ) as crear:
        resultado = incidentes_service.procesar_incidente_de_alerta(
            alerta=alerta,
            id_envio=3,
            id_sensor=1,
            id_lectura="lectura-test-001",
            tipo="Temperatura alta",
            severidad="Alta",
            descripcion="Temperatura elevada",
        )

    assert resultado == (10, "reutilizado")
    crear.assert_not_called()


def test_incidente_de_otro_tipo_no_se_reutiliza():
    alerta = {
        "_id": "507f1f77bcf86cd799439011",
        "incidente_id": 10,
    }

    incidente_incorrecto = (
        10,
        3,
        "Temperatura alta",
        datetime.now(timezone.utc),
        "Alta",
        "Abierto",
        "Temperatura elevada | Sensor 1 "
        "[lectura:lectura-test-001]",
    )

    with patch.object(
        incidentes_service,
        "buscar_incidente",
        return_value=incidente_incorrecto,
    ), patch.object(
        incidentes_service,
        "existe_incidente_por_lectura",
        return_value=None,
    ), patch.object(
        incidentes_service,
        "obtener_o_crear_incidente_iot",
        return_value=(11, True),
    ), patch.object(
        incidentes_service,
        "vincular_incidente_alerta",
    ) as vincular:
        resultado = incidentes_service.procesar_incidente_de_alerta(
            alerta=alerta,
            id_envio=3,
            id_sensor=1,
            id_lectura="lectura-test-001",
            tipo="Batería baja",
            severidad="Media",
            descripcion="Batería insuficiente",
        )

    assert resultado == (11, "creado")
    vincular.assert_called_once_with(alerta["_id"], 11)


def test_incidente_antiguo_del_mismo_tipo_se_recupera():
    alerta = {
        "_id": "507f1f77bcf86cd799439011",
        "incidente_id": None,
    }

    incidente_antiguo = (
        10,
        3,
        "Temperatura alta",
        datetime.now(timezone.utc),
        "Alta",
        "Abierto",
        "Temperatura elevada | Sensor 1 "
        "[lectura:lectura-test-001]",
    )

    with patch.object(
        incidentes_service,
        "existe_incidente_por_lectura",
        return_value=10,
    ), patch.object(
        incidentes_service,
        "buscar_incidente",
        return_value=incidente_antiguo,
    ), patch.object(
        incidentes_service,
        "vincular_incidente_alerta",
    ) as vincular:
        resultado = incidentes_service.procesar_incidente_de_alerta(
            alerta=alerta,
            id_envio=3,
            id_sensor=1,
            id_lectura="lectura-test-001",
            tipo="Temperatura alta",
            severidad="Alta",
            descripcion="Temperatura elevada",
        )

    assert resultado == (10, "recuperado")
    vincular.assert_called_once_with(alerta["_id"], 10)


# ------------------------------------------------------------ evento vigente de la alerta

def test_alerta_con_envio_guarda_el_ultimo_evento_vigente():
    from bson import ObjectId
    coleccion = MagicMock()
    coleccion.find_one.return_value = {"_id": "a1"}
    evento = {"_id": ObjectId("6720f0a1b2c3d4e5f6a7b8c9"), "tipo": "ADUANA"}
    with patch.object(alerta_repository, "coleccion_alertas", return_value=coleccion), \
         patch.object(alerta_repository, "ultimo_evento_envio", return_value=evento) as ultimo:
        alerta_repository.registrar_alerta(1, 2, "Temperatura alta", "Alta", "d", "L1", envio_id=14)
    id_envio, momento = ultimo.call_args.args
    assert id_envio == 14
    insertado = coleccion.update_one.call_args.args[1]["$setOnInsert"]
    assert insertado["evento_id"] == "6720f0a1b2c3d4e5f6a7b8c9"
    assert insertado["fecha"] == momento          # el evento vigente al detectar


def test_alerta_sin_envio_o_sin_eventos_queda_sin_evento():
    coleccion = MagicMock()
    coleccion.find_one.return_value = {"_id": "a1"}
    with patch.object(alerta_repository, "coleccion_alertas", return_value=coleccion), \
         patch.object(alerta_repository, "ultimo_evento_envio", return_value=None) as ultimo:
        alerta_repository.registrar_alerta(1, 2, "Temperatura alta", "Alta", "d", "L1", envio_id=None)
        ultimo.assert_not_called()
        alerta_repository.registrar_alerta(1, 2, "Batería baja", "Media", "d", "L2", envio_id=14)
    for llamada in coleccion.update_one.call_args_list:
        assert llamada.args[1]["$setOnInsert"]["evento_id"] is None


def test_ultimo_evento_busca_el_mas_reciente_hasta_la_deteccion():
    from app.repositories import evento_repository
    coleccion = MagicMock()
    momento = datetime(2026, 10, 31, 17, 0, tzinfo=timezone.utc)
    with patch.object(evento_repository, "get_mongo_database",
                      return_value={"eventos_logisticos": coleccion}):
        evento_repository.ultimo_evento_envio(14, momento)
    filtro = coleccion.find_one.call_args.args[0]
    assert filtro == {"envio_id": 14, "fecha_hora": {"$lte": momento}}
    assert coleccion.find_one.call_args.kwargs["sort"][0] == ("fecha_hora", -1)


def test_consultar_alertas_muestra_el_ultimo_evento(capsys):
    alertas = [
        {"_id": "a1", "tipo": "Temperatura alta", "severidad": "Alta", "estado": "Activa",
         "fecha": datetime(2026, 10, 31, 18, 0, tzinfo=timezone.utc), "sensor_id": 35,
         "envio_id": 14, "evento_id": "e1", "descripcion": "Temperatura alta: valor 9,78, límite 8"},
        {"_id": "a2", "tipo": "Batería baja", "severidad": "Media", "estado": "Activa",
         "fecha": datetime(2026, 10, 31, 18, 5, tzinfo=timezone.utc), "sensor_id": 36,
         "envio_id": None, "evento_id": None, "descripcion": "Batería baja: valor 10, límite 20"},
    ]
    eventos = {"e1": {"_id": "e1", "tipo": "ADUANA",
                      "fecha_hora": datetime(2026, 10, 31, 17, 0, tzinfo=timezone.utc)}}
    with patch.object(incidentes_service, "listar_alertas", return_value=alertas), \
         patch.object(incidentes_service, "buscar_eventos_por_id", return_value=eventos) as buscar, \
         patch("builtins.input", side_effect=["1", "", ""]):
        incidentes_service.consultar_alertas_service()
    salida = capsys.readouterr().out
    assert "Último evento: Aduana, 31/10/2026 14:00" in salida
    assert salida.count("Último evento") == 1        # la alerta sin evento no muestra la línea
    buscar.assert_called_once_with({"e1"})
