class Rol:
    def __init__(self, descripcion, nivel_permisos):
        self.descripcion = descripcion
        self.nivel_permisos = nivel_permisos

    def __str__(self):
        return (
            f"Descripción: {self.descripcion}\n"
            f"Nivel de permisos: {self.nivel_permisos}"
        )