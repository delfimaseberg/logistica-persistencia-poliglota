from app.utils import formato


class Contenedor:
    def __init__(
        self,
        codigo_internacional,
        tipo,
        capacidad,
        estado
    ):
        self.codigo_internacional = codigo_internacional
        self.tipo = tipo
        self.capacidad = capacidad
        self.estado = estado

    def __str__(self):
        return (
            f"Código internacional: {self.codigo_internacional}\n"
            f"Tipo: {self.tipo}\n"
            f"Capacidad: {formato.compacto(self.capacidad)} toneladas\n"
            f"Estado: {self.estado}"
        )