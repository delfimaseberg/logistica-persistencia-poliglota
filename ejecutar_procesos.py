
import argparse
from datetime import datetime

from app.services.procesos_periodicos_service import (
    ejecutar_todos_los_procesos,
)
from app.utils.logger import obtener_logger


logger = obtener_logger("ejecutar_procesos")


TRABAJOS = {
    "sensores": ("sensores",),
    "predicciones": ("predicciones",),
    "todos": ("predicciones", "sensores"),
}

# Trabajos financieros: se ejecutan solo cuando se piden explícitamente
# (no forman parte de "todos").
TRABAJOS_FINANCIEROS = ("facturacion", "cierre")


def _fecha(texto):
    try:
        return datetime.strptime(texto, "%Y-%m-%d").date()
    except ValueError:
        raise argparse.ArgumentTypeError("Use el formato AAAA-MM-DD.")


def _periodo(texto):
    try:
        return datetime.strptime(texto, "%Y-%m").date()
    except ValueError:
        raise argparse.ArgumentTypeError("Use el formato AAAA-MM.")


def ejecutar_facturacion(fecha_corte=None):
    from app.services.facturacion_automatica_service import (
        procesar_facturacion_automatica,
    )

    resumen = procesar_facturacion_automatica(fecha_corte)
    print()
    print(f"Facturación automática (corte {resumen['fecha_corte']}):")
    print(f"  Candidatos: {resumen['candidatos']}")
    print(f"  Facturados: {len(resumen['facturados'])}")
    for f in resumen["facturados"]:
        print(f"    Envío {f['id_envio']} -> factura {f['id_factura']} "
              f"({f['total']})")
    print(f"  Omitidos: {len(resumen['omitidos'])}")
    for o in resumen["omitidos"]:
        print(f"    Envío {o['id_envio']}: {o['motivo']}")
    print(f"  Errores: {len(resumen['errores'])}")
    for e in resumen["errores"]:
        print(f"    Envío {e['id_envio']}: {e['error']}")
    return 1 if resumen["errores"] else 0


def ejecutar_cierre(periodo):
    from app.services.cierre_cuenta_service import cerrar_mes_todos

    resumen = cerrar_mes_todos(periodo)
    print()
    print(f"Cierre mensual {periodo:%Y-%m}:")
    print(f"  Cerrados: {len(resumen['cerrados'])}")
    for c in resumen["cerrados"]:
        print(f"    {c['cliente']}: saldo final {c['saldo_final']}")
    print(f"  Bloqueados: {len(resumen['bloqueados'])}")
    for b in resumen["bloqueados"]:
        print(f"    {b['cliente']}: {b['motivo']}")
    print(f"  Ya cerrados: {len(resumen['ya_cerrados'])}")
    print(f"  Errores: {len(resumen['errores'])}")
    for e in resumen["errores"]:
        print(f"    {e['cliente']}: {e['error']}")
    return 1 if resumen["errores"] else 0


def hay_errores(resultado):
    """Incluye fallos generales y fallos individuales de cada trabajo."""
    if resultado.get("errores"):
        return True

    predicciones = resultado.get("predicciones")
    if predicciones is not None and predicciones.get("errores", 0):
        return True

    sensores = resultado.get("sensores")
    if sensores is not None and sensores.get("errores"):
        return True

    return False


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Ejecuta procesos periódicos de logística."
    )
    parser.add_argument(
        "--job",
        choices=tuple(TRABAJOS) + TRABAJOS_FINANCIEROS,
        default="todos",
        help="Trabajo a ejecutar (por defecto: todos).",
    )
    parser.add_argument(
        "--horas-sensores",
        type=float,
        default=24,
        help="Umbral de horas sin lecturas para sensores (por defecto: 24).",
    )
    parser.add_argument(
        "--corte",
        type=_fecha,
        default=None,
        help="Facturación: fecha de corte AAAA-MM-DD (por defecto, hoy).",
    )
    parser.add_argument(
        "--periodo",
        type=_periodo,
        default=None,
        help="Cierre: período a cerrar AAAA-MM (obligatorio con --job cierre).",
    )
    argumentos = parser.parse_args(argv)

    if argumentos.job in TRABAJOS_FINANCIEROS:
        logger.info("Inicio de proceso financiero: %s", argumentos.job)
        try:
            if argumentos.job == "facturacion":
                return ejecutar_facturacion(argumentos.corte)
            if argumentos.periodo is None:
                parser.error("--job cierre requiere --periodo AAAA-MM")
            return ejecutar_cierre(argumentos.periodo)
        except SystemExit:
            raise
        except Exception:
            logger.exception("Error en el proceso %s", argumentos.job)
            return 1

    logger.info(
        "Inicio de procesos periódicos: trabajos=%s",
        ",".join(TRABAJOS[argumentos.job]),
    )

    try:
        resultado = ejecutar_todos_los_procesos(
            horas_sensores=argumentos.horas_sensores,
            procesos=TRABAJOS[argumentos.job],
        )

        predicciones = resultado.get("predicciones")
        sensores = resultado.get("sensores")
        errores = resultado.get("errores", {})

        if predicciones is not None:
            print("\nPredicciones diarias:")
            print(f"  Guardadas: {predicciones.get('guardadas', 0)}")
            print(
                f"  Riesgos altos: "
                f"{predicciones.get('riesgos_altos', 0)}"
            )
            print(f"  Errores: {predicciones.get('errores', 0)}")

        if sensores is not None:
            print("\nRevisión de sensores:")
            print(f"  Sensores activos: {sensores['sensores_activos']}")
            print(f"  Al día: {sensores['al_dia']}")
            print(f"  Sin lecturas: {len(sensores['sin_lecturas'])}")
            print(f"  Con lecturas atrasadas: {len(sensores['atrasados'])}")
            print(f"  Alertas procesadas: {sensores['alertas_procesadas']}")
            print(f"  Errores: {len(sensores['errores'])}")

        if errores:
            print("\nProcesos con errores:")
            for proceso, detalle in errores.items():
                print(f"  {proceso}: {detalle}")

        hubo_errores = hay_errores(resultado)
        logger.info(
            "Finalizaron los procesos periódicos: estado=%s",
            "con_errores" if hubo_errores else "correcto",
        )
        return 1 if hubo_errores else 0

    except Exception:
        logger.exception("Error al ejecutar los procesos periódicos")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
