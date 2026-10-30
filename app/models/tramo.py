class Tramo:
    def __init__(
        self,
        id_envio,
        id_vehiculo,
        medio_transporte,
        origen,
        destino,
        fecha_salida,
        fecha_estimada_llegada,
        id_operador=None
    ):
        self.id_envio = id_envio
        self.id_vehiculo = id_vehiculo
        self.medio_transporte = medio_transporte
        self.origen = origen
        self.destino = destino
        self.fecha_salida = fecha_salida
        self.fecha_estimada_llegada = fecha_estimada_llegada
        # Operador logístico que realiza el tramo.
        self.id_operador = id_operador

    def __str__(self):
        return (
            f"Envío ID: {self.id_envio}\n"
            f"Vehículo ID: {self.id_vehiculo}\n"
            f"Operador ID: {self.id_operador}\n"
            f"Medio de transporte: {self.medio_transporte}\n"
            f"Origen: {self.origen}\n"
            f"Destino: {self.destino}\n"
            f"Fecha de salida: {self.fecha_salida}\n"
            f"Fecha estimada de llegada: {self.fecha_estimada_llegada}"
        )
