from app.repositories.lectura_iot_repository import (
    abrir_conexion,
    cerrar_conexion
)


def consultar_gps_contenedor(id_contenedor, meses, limite_por_mes=2000):
    """Posiciones GPS de un contenedor desde Cassandra.

    Consulta una partición (contenedor, mes) por cada mes pedido y
    devuelve solo las lecturas que tienen posición, en orden
    cronológico.
    """
    cluster = None
    session = None

    try:
        cluster, session = abrir_conexion()

        consulta = session.prepare("""
            SELECT fecha_hora, sensor_id, gps_latitud, gps_longitud
            FROM lecturas_por_contenedor
            WHERE contenedor_id = ?
              AND anio_mes = ?
            LIMIT ?
        """)

        puntos = []

        for anio_mes in meses:
            filas = session.execute(
                consulta,
                (int(id_contenedor), anio_mes, int(limite_por_mes))
            )

            for fila in filas:
                if (
                    fila.gps_latitud is None
                    or fila.gps_longitud is None
                ):
                    continue

                puntos.append({
                    "fecha_hora": fila.fecha_hora,
                    "sensor_id": fila.sensor_id,
                    "lat": fila.gps_latitud,
                    "lon": fila.gps_longitud
                })

        puntos.sort(key=lambda p: p["fecha_hora"])
        return puntos

    finally:
        cerrar_conexion(cluster, session)
