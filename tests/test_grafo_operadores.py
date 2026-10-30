from unittest.mock import MagicMock, patch

from app.repositories import grafo_repository
from app.services import sincronizacion_service
from app.services import tramo_service


OPERADOR = {
    "id_operador": 1, "razon_social": "Transportes Andinos S.A.",
    "modalidades": ["Terrestre"], "estado": "ACTIVO",
}


def datos(operador=OPERADOR, operador_vehiculo=None):
    return {
        "envio": {"id_envio": 9, "estado": "Entregado", "prioridad": "Media",
                  "origen": "A", "destino": "B",
                  "fecha_creacion": "2026-09-01T00:00:00+00:00"},
        "cliente": {"id_cliente": 3, "razon_social": "C", "pais": "Argentina"},
        "tramos": [{
            "id_tramo": 5, "medio_transporte": "Terrestre",
            "origen": "A", "destino": "B",
            "fecha_salida": "2026-09-02T00:00:00+00:00",
            "fecha_estimada_llegada": "2026-09-03T00:00:00+00:00",
            "id_vehiculo": 1, "identificacion": "AB123CD",
            "tipo_vehiculo": "Terrestre",
            "operador": operador,
            "operador_vehiculo": operador_vehiculo,
        }],
        "contenedores": [],
    }


def consultas(tx):
    return [(c.args[0], c.kwargs) for c in tx.run.call_args_list]


def test_tramo_con_operador_genera_realizado_por():
    tx = MagicMock()
    grafo_repository._sincronizar_tx(tx, datos())
    realizadas = [(q, kw) for q, kw in consultas(tx) if "MERGE (t)-[:REALIZADO_POR]->(op)" in q]
    assert len(realizadas) == 1
    consulta, parametros = realizadas[0]
    assert "MERGE (op:Operador {id_operador: $op.id_operador})" in consulta
    assert parametros["op"] == OPERADOR
    assert parametros["id_tramo"] == 5


def test_tramo_sin_operador_no_crea_operador():
    tx = MagicMock()
    grafo_repository._sincronizar_tx(tx, datos(operador=None))
    assert not any("MERGE (op:Operador" in q for q, _ in consultas(tx))


def test_ya_no_se_crean_operadores_por_nombre():
    tx = MagicMock()
    grafo_repository._sincronizar_tx(tx, datos(operador_vehiculo=OPERADOR))
    assert not any("{nombre: $operador_norm}" in q for q, _ in consultas(tx))
    assert any("MERGE (v)-[:OPERADO_POR]->(op)" in q for q, _ in consultas(tx))


def test_limpieza_solo_borra_operadores_sin_id():
    tx = MagicMock()
    tx.run.return_value.single.return_value = {"eliminados": 1}
    assert grafo_repository._eliminar_operadores_legados_tx(tx) == 1
    consulta = tx.run.call_args.args[0]
    assert "MATCH (op:Operador)" in consulta
    assert "WHERE op.id_operador IS NULL" in consulta
    assert "DETACH DELETE op" in consulta


def test_resincronizar_limpia_legados_solo_si_todo_salio_bien():
    with patch.object(sincronizacion_service, "listar_ids_envios", return_value=[1, 2]), \
         patch.object(sincronizacion_service, "reconciliar_envio"), \
         patch.object(sincronizacion_service, "resolver_pendientes_envio"), \
         patch.object(sincronizacion_service, "eliminar_operadores_legados",
                      return_value=1) as limpiar:
        assert sincronizacion_service.resincronizar_todos() == (2, [])
    limpiar.assert_called_once()

    with patch.object(sincronizacion_service, "listar_ids_envios", return_value=[1]), \
         patch.object(sincronizacion_service, "reconciliar_envio",
                      side_effect=RuntimeError("caído")), \
         patch.object(sincronizacion_service, "_marcar_pendiente"), \
         patch.object(sincronizacion_service, "eliminar_operadores_legados") as limpiar:
        correctos, errores = sincronizacion_service.resincronizar_todos()
    assert correctos == 0 and len(errores) == 1
    limpiar.assert_not_called()


def test_consulta_contenedor_filtra_por_cliente():
    tx = MagicMock()
    tx.run.return_value = []
    grafo_repository._operadores_contenedor_tx(tx, 2, 4)
    consulta = tx.run.call_args.args[0]
    assert "$id_cliente IS NULL OR cl.id_cliente = $id_cliente" in consulta
    assert tx.run.call_args.kwargs == {"id_contenedor": 2, "id_cliente": 4}


def test_red_cliente_no_expone_otros_clientes():
    tx = MagicMock()
    tx.run.return_value = []
    grafo_repository._red_cliente_tx(tx, 4)
    consulta = tx.run.call_args.args[0]
    assert "count(DISTINCT otro) AS otros_clientes" in consulta
    assert "otro.razon_social" not in consulta


# ------------------------------------------- operador al registrar tramo

OPERADORES = [(1, "Transportes Andinos S.A."), (3, "AeroCarga Sur S.A.")]


def vehiculo(id_operador):
    return (1, "Terrestre", "AB123CD", None, "Disponible", id_operador, None)


def test_tramo_toma_el_operador_del_vehiculo():
    with patch.object(tramo_service, "listar_operadores_por_modalidad",
                      return_value=OPERADORES), \
         patch("builtins.input") as entrada:
        assert tramo_service.elegir_operador_tramo(vehiculo(1), "Terrestre") == (
            1, "Transportes Andinos S.A.")
    entrada.assert_not_called()


def test_tramo_pide_operador_si_el_vehiculo_no_tiene():
    with patch.object(tramo_service, "listar_operadores_por_modalidad",
                      return_value=OPERADORES), \
         patch("builtins.input", side_effect=["9", "3"]):
        assert tramo_service.elegir_operador_tramo(vehiculo(None), "Terrestre") == (
            3, "AeroCarga Sur S.A.")


def test_tramo_sin_operadores_de_la_modalidad():
    with patch.object(tramo_service, "listar_operadores_por_modalidad",
                      return_value=[]):
        assert tramo_service.elegir_operador_tramo(vehiculo(None), "Aéreo") is None
