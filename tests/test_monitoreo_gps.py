from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

from app.services import monitoreo_avanzado_service as service


SENSOR_GPS = (52, 8, "CONT-IT-8", "GPS", "Marca", None, "Activo")
SENSOR_TEMPERATURA = (53, 8, "CONT-IT-8", "temperatura", "Marca", None, "Activo")
CONTENEDOR = (8, "CONT-IT-8", "General", 10, "Activo")


def _preparar(monkeypatch, entradas):
    valores = iter(entradas)
    monkeypatch.setattr(service, "input", lambda _mensaje="": next(valores), raising=False)
    monkeypatch.setattr(service, "pausar", lambda: None)


def _posicion():
    return SimpleNamespace(
        fecha_hora=datetime(2026, 10, 27, 12, tzinfo=timezone.utc),
        gps_latitud=-34.6,
        gps_longitud=-58.4,
    )


def test_consulta_por_contenedor_muestra_sensor_y_posiciones(monkeypatch, capsys):
    _preparar(monkeypatch, ["1", "8", "2026-10", ""])
    monkeypatch.setattr(service, "buscar_contenedor_por_id", lambda _id: CONTENEDOR)
    monkeypatch.setattr(service, "listar_sensores_por_contenedor", lambda _id: [SENSOR_GPS])
    consultas = []
    monkeypatch.setattr(
        service,
        "consultar_lecturas_sensor_db",
        lambda *args, **kwargs: consultas.append((args, kwargs)) or [_posicion()],
    )

    service.consultar_posiciones_gps_service()

    salida = capsys.readouterr().out
    assert "Contenedor ID: 8" in salida
    assert "CONT-IT-8" in salida
    assert "Sensor GPS asociado: 52" in salida
    assert "Lat: -34.6" in salida and "Lon: -58.4" in salida
    assert len(consultas) == 1
    assert consultas[0][0] == (52, "2026-10")


def test_contenedor_inexistente_no_consulta_sensores(monkeypatch, capsys):
    _preparar(monkeypatch, ["1", "999"])
    monkeypatch.setattr(service, "buscar_contenedor_por_id", lambda _id: None)
    listar = Mock(wraps=service.listar_sensores_por_contenedor)
    monkeypatch.setattr(service, "listar_sensores_por_contenedor", listar)

    service.consultar_posiciones_gps_service()

    assert "No existe ese contenedor" in capsys.readouterr().out
    listar.assert_not_called()


def test_contenedor_sin_sensor_gps_no_elige_otro_sensor(monkeypatch, capsys):
    _preparar(monkeypatch, ["1", "8"])
    monkeypatch.setattr(service, "buscar_contenedor_por_id", lambda _id: CONTENEDOR)
    monkeypatch.setattr(
        service,
        "listar_sensores_por_contenedor",
        lambda _id: [SENSOR_TEMPERATURA],
    )
    consultar = Mock(wraps=service.consultar_lecturas_sensor_db)
    monkeypatch.setattr(service, "consultar_lecturas_sensor_db", consultar)

    service.consultar_posiciones_gps_service()

    assert "no tiene un sensor GPS asociado" in capsys.readouterr().out
    consultar.assert_not_called()


def test_contenedor_con_varios_gps_exige_seleccion_explicita(monkeypatch, capsys):
    sensor_gps_2 = (54, 8, "CONT-IT-8", "GPS", "Otra marca", None, "Activo")
    _preparar(monkeypatch, ["1", "8", "54", "2026-10", ""])
    monkeypatch.setattr(service, "buscar_contenedor_por_id", lambda _id: CONTENEDOR)
    monkeypatch.setattr(
        service,
        "listar_sensores_por_contenedor",
        lambda _id: [SENSOR_GPS, sensor_gps_2],
    )
    consultas = Mock(return_value=[_posicion()])
    monkeypatch.setattr(service, "consultar_lecturas_sensor_db", consultas)

    service.consultar_posiciones_gps_service()

    salida = capsys.readouterr().out
    assert "varios sensores GPS" in salida
    assert "Sensor GPS asociado: 54" in salida
    assert consultas.call_args.args[0] == 54


def test_sensor_gps_sin_posiciones_informa_ausencia_de_datos(monkeypatch, capsys):
    _preparar(monkeypatch, ["1", "8", "2026-10"])
    monkeypatch.setattr(service, "buscar_contenedor_por_id", lambda _id: CONTENEDOR)
    monkeypatch.setattr(service, "listar_sensores_por_contenedor", lambda _id: [SENSOR_GPS])
    monkeypatch.setattr(service, "consultar_lecturas_sensor_db", lambda *_args, **_kwargs: [])

    service.consultar_posiciones_gps_service()

    salida = capsys.readouterr().out
    assert "Sensor GPS asociado: 52" in salida
    assert "No hay posiciones GPS registradas" in salida


def test_consulta_por_sensor_muestra_contenedor_y_abre_google_maps(monkeypatch, capsys):
    _preparar(monkeypatch, ["2", "52", "2026-10", "1"])
    monkeypatch.setattr(service, "buscar_sensor_por_id", lambda _id: SENSOR_GPS)
    monkeypatch.setattr(service, "buscar_contenedor_por_id", lambda _id: CONTENEDOR)
    monkeypatch.setattr(service, "consultar_lecturas_sensor_db", lambda *_args, **_kwargs: [_posicion()])
    abrir = Mock(wraps=service.webbrowser.open)
    monkeypatch.setattr(service.webbrowser, "open", abrir)

    service.consultar_posiciones_gps_service()

    salida = capsys.readouterr().out
    assert "Contenedor ID: 8" in salida
    assert "Sensor GPS asociado: 52" in salida
    assert "google.com/maps/search" in salida
    abrir.assert_called_once()
    assert "-34.6%2C-58.4" in abrir.call_args.args[0]


def test_consulta_por_sensor_rechaza_sensor_no_gps(monkeypatch, capsys):
    _preparar(monkeypatch, ["2", "53"])
    monkeypatch.setattr(service, "buscar_sensor_por_id", lambda _id: SENSOR_TEMPERATURA)
    buscar_contenedor = Mock(wraps=service.buscar_contenedor_por_id)
    monkeypatch.setattr(service, "buscar_contenedor_por_id", buscar_contenedor)

    service.consultar_posiciones_gps_service()

    assert "no es de tipo GPS" in capsys.readouterr().out
    buscar_contenedor.assert_not_called()
