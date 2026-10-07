class Vehiculo:
    def __init__(
        self,
        tipo,
        identificacion,
        empresa_operadora,
        estado
    ):
        self.tipo = tipo
        self.identificacion = identificacion
        self.empresa_operadora = empresa_operadora
        self.estado = estado

    def __str__(self):
        return (
            f"Tipo: {self.tipo}\n"
            f"Identificación: {self.identificacion}\n"
            f"Empresa operadora: {self.empresa_operadora}\n"
            f"Estado: {self.estado}"
        )