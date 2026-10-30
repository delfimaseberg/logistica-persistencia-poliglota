class Vehiculo:
    def __init__(
        self,
        tipo,
        identificacion,
        empresa_operadora,
        estado,
        id_operador=None
    ):
        self.tipo = tipo
        self.identificacion = identificacion
        # Texto histórico (anterior a la migración 010). No se escribe más.
        self.empresa_operadora = empresa_operadora
        self.estado = estado
        self.id_operador = id_operador

    def __str__(self):
        return (
            f"Tipo: {self.tipo}\n"
            f"Identificación: {self.identificacion}\n"
            f"Operador ID: {self.id_operador}\n"
            f"Estado: {self.estado}"
        )
