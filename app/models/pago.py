class Pago:
    def __init__(
        self,
        id_factura,
        monto,
        metodo_pago
    ):
        self.id_factura = id_factura
        self.monto = monto
        self.metodo_pago = metodo_pago

    def __str__(self):
        return (
            f"Factura ID: {self.id_factura}\n"
            f"Monto: {self.monto}\n"
            f"Método de pago: {self.metodo_pago}"
        )