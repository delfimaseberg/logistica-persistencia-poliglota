class Factura:
    def __init__(
        self,
        id_cliente,
        fecha_emision,
        total,
        estado
    ):
        self.id_cliente = id_cliente
        self.fecha_emision = fecha_emision
        self.total = total
        self.estado = estado

    def __str__(self):
        return (
            f"Cliente ID: {self.id_cliente}\n"
            f"Fecha de emisión: {self.fecha_emision}\n"
            f"Total: {self.total}\n"
            f"Estado: {self.estado}"
        )