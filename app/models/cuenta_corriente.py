class CuentaCorriente:
    def __init__(
        self,
        id_cliente,
        saldo=0
    ):
        self.id_cliente = id_cliente
        self.saldo = saldo

    def __str__(self):
        return (
            f"Cliente ID: {self.id_cliente}\n"
            f"Saldo: {self.saldo}"
        )