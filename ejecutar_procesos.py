
import argparse

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
        choices=tuple(TRABAJOS),
        default="todos",
        help="Trabajo a ejecutar (por defecto: todos).",
    )
    parser.add_argument(
        "--horas-sensores",
        type=float,
        default=24,
        help="Umbral de horas sin lecturas para sensores (por defecto: 24).",
    )
    argumentos = parser.parse_args(argv)

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
