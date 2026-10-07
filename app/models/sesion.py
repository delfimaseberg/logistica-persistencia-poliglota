class Sesion:
    def __init__(self, id_usuario, estado, fecha_fin=None):
        self.id_usuario = id_usuario
        self.estado = estado
        self.fecha_fin = fecha_fin

    def __str__(self):
        return (
            f"Usuario ID: {self.id_usuario}\n"
            f"Estado: {self.estado}\n"
            f"Fecha de fin: {self.fecha_fin if self.fecha_fin else 'Sesión activa'}"
        )