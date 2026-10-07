class Usuario:
    def __init__(
        self,
        id_cliente,
        id_rol,
        nombre,
        apellido,
        email,
        contrasena_encriptada,
        estado
    ):
        self.id_cliente = id_cliente
        self.id_rol = id_rol
        self.nombre = nombre
        self.apellido = apellido
        self.email = email
        self.contrasena_encriptada = contrasena_encriptada
        self.estado = estado

    def __str__(self):
        return (
            f"Cliente ID: {self.id_cliente}\n"
            f"Rol ID: {self.id_rol}\n"
            f"Nombre: {self.nombre}\n"
            f"Apellido: {self.apellido}\n"
            f"Email: {self.email}\n"
            f"Estado: {self.estado}"
        )