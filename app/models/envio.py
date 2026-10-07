class Envio:
    def __init__(
        self,
        id_cliente,
        origen,
        destino,
        estado,
        prioridad
    ):
        self.id_cliente = id_cliente
        self.origen = origen
        self.destino = destino
        self.estado = estado
        self.prioridad = prioridad

    def __str__(self):
        return (
            f"Cliente ID: {self.id_cliente}\n"
            f"Origen: {self.origen}\n"
            f"Destino: {self.destino}\n"
            f"Estado: {self.estado}\n"
            f"Prioridad: {self.prioridad}"
        )