"""ejecutar_procesos.py --job facturacion / --job cierre."""

from datetime import date
from unittest.mock import patch

import pytest

import ejecutar_procesos


def resumen_facturacion(errores=()):
    return {"fecha_corte": date(2026, 10, 31), "candidatos": 1,
            "facturados": [{"id_envio": 45, "id_factura": 900, "total": 10}],
            "omitidos": [], "errores": list(errores)}


def test_job_facturacion_pasa_el_corte_y_devuelve_cero():
    with patch("app.services.facturacion_automatica_service."
               "procesar_facturacion_automatica",
               return_value=resumen_facturacion()) as procesar, \
         patch.object(ejecutar_procesos, "ejecutar_todos_los_procesos") as otros:
        codigo = ejecutar_procesos.main(["--job", "facturacion", "--corte", "2026-10-31"])
    assert codigo == 0
    procesar.assert_called_once_with(date(2026, 10, 31))
    otros.assert_not_called()


def test_job_facturacion_sin_corte_usa_el_valor_por_defecto():
    with patch("app.services.facturacion_automatica_service."
               "procesar_facturacion_automatica",
               return_value=resumen_facturacion()) as procesar:
        ejecutar_procesos.main(["--job", "facturacion"])
    procesar.assert_called_once_with(None)


def test_job_facturacion_con_errores_devuelve_uno():
    with patch("app.services.facturacion_automatica_service."
               "procesar_facturacion_automatica",
               return_value=resumen_facturacion(
                   [{"id_envio": 46, "error": "x"}])):
        assert ejecutar_procesos.main(["--job", "facturacion"]) == 1


def test_job_cierre_exige_periodo():
    with pytest.raises(SystemExit):
        ejecutar_procesos.main(["--job", "cierre"])


def test_job_cierre_con_periodo():
    resumen = {"periodo": date(2026, 10, 1), "cerrados": [], "bloqueados": [],
               "ya_cerrados": [], "errores": []}
    with patch("app.services.cierre_cuenta_service.cerrar_mes_todos",
               return_value=resumen) as cerrar:
        assert ejecutar_procesos.main(["--job", "cierre", "--periodo", "2026-10"]) == 0
    cerrar.assert_called_once_with(date(2026, 10, 1))


def test_formato_invalido_de_corte():
    with pytest.raises(SystemExit):
        ejecutar_procesos.main(["--job", "facturacion", "--corte", "31/10/2026"])


def test_todos_no_incluye_trabajos_financieros():
    assert ejecutar_procesos.TRABAJOS["todos"] == ("predicciones", "sensores")
