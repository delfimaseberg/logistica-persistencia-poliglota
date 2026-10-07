class Incidente:
    def __init__(
        self,
        id_envio,
        tipo,
        severidad,
        estado,
        descripcion
    ):
        self.id_envio = id_envio
        self.tipo = tipo
        self.severidad = severidad
        self.estado = estado
        self.descripcion = descripcion

    def __str__(self):
        return (
            f"Envío ID: {self.id_envio}\n"
            f"Tipo: {self.tipo}\n"
            f"Severidad: {self.severidad}\n"
            f"Estado: {self.estado}\n"
            f"Descripción: {self.descripcion}"
        )