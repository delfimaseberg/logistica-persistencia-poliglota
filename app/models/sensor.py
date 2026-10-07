class Sensor:
    def __init__(
        self,
        id_contenedor,
        tipo,
        fabricante,
        fecha_instalacion,
        estado
    ):
        self.id_contenedor = id_contenedor
        self.tipo = tipo
        self.fabricante = fabricante
        self.fecha_instalacion = fecha_instalacion
        self.estado = estado

    def __str__(self):
        return (
            f"Contenedor ID: {self.id_contenedor}\n"
            f"Tipo: {self.tipo}\n"
            f"Fabricante: {self.fabricante}\n"
            f"Fecha de instalación: {self.fecha_instalacion}\n"
            f"Estado: {self.estado}"
        )