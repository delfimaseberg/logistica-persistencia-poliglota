"""015 (datos): alertas "sin transmisión" de contenedores ya entregados.

Pasa a Atendida, con la nota "contenedor ya entregado", las alertas activas
"Sensor sin transmisión reciente" de contenedores cuyos envíos están todos
Entregados (sus sensores dejaron de transmitir porque terminó el viaje). No
borra nada.

Uso (desde la raíz del proyecto):
    python scripts/migrations/015_atender_alertas_entregados.py            # solo cuenta
    python scripts/migrations/015_atender_alertas_entregados.py --aplicar  # actualiza
    python scripts/migrations/015_atender_alertas_entregados.py --aplicar --esperadas 21
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.database.postgres_connection import get_postgres_connection  # noqa: E402
from app.repositories.alerta_repository import atender_alertas_de_contenedores  # noqa: E402


TIPOS = "sin transmisi"
NOTA = "contenedor ya entregado"


def contenedores_entregados():
    """Contenedores con al menos un envío y todos sus envíos Entregados."""
    with get_postgres_connection() as conexion, conexion.cursor() as cursor:
        cursor.execute("SELECT current_database()")
        print("Base PostgreSQL:", cursor.fetchone()[0])
        cursor.execute("""
            SELECT ec.id_contenedor
            FROM envio_contenedor ec
            JOIN envio e ON e.id_envio = ec.id_envio
            GROUP BY ec.id_contenedor
            HAVING bool_and(e.estado = 'Entregado')
            ORDER BY ec.id_contenedor
        """)
        return [fila[0] for fila in cursor.fetchall()]


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--aplicar", action="store_true")
    parser.add_argument("--esperadas", type=int, default=None,
                        help="Cantidad esperada; si no coincide, no se modifica nada.")
    args = parser.parse_args(argv)

    contenedores = contenedores_entregados()
    print("Contenedores entregados:", contenedores)
    cantidad = atender_alertas_de_contenedores(TIPOS, contenedores, NOTA, aplicar=False)
    print("Alertas activas a pasar a Atendida:", cantidad)

    if args.esperadas is not None and cantidad != args.esperadas:
        print(f"Se esperaban {args.esperadas}; no se modifica nada.")
        return 1
    if not args.aplicar:
        print("Sin --aplicar: no se modificó nada.")
        return 0
    modificadas = atender_alertas_de_contenedores(TIPOS, contenedores, NOTA, aplicar=True)
    print("Alertas pasadas a Atendida:", modificadas)
    return 0 if modificadas == cantidad else 1


if __name__ == "__main__":
    sys.exit(main())
