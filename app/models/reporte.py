class Reporte:
    def __init__(
        self,
        id_usuario,
        tipo,
        formato,
        estado
    ):
        self.id_usuario = id_usuario
        self.tipo = tipo
        self.formato = formato
        self.estado = estado

    def __str__(self):
        return (
            f"Usuario ID: {self.id_usuario}\n"
            f"Tipo: {self.tipo}\n"
            f"Formato: {self.formato}\n"
            f"Estado: {self.estado}"
        )