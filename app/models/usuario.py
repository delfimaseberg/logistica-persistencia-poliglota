from app.utils.validaciones_terceros import (
    describir_parte,
    validar_partes_usuario
)


class Usuario:
    """Usuario del sistema.

    Pertenece como mucho a una parte: un cliente, un proveedor o un
    operador logístico. Si no tiene ninguna es un usuario interno.
    """

    def __init__(
        self,
        id_cliente,
        id_rol,
        nombre,
        apellido,
        email,
        contrasena_encriptada,
        estado,
        id_proveedor=None,
        id_operador=None
    ):
        validar_partes_usuario(id_cliente, id_proveedor, id_operador)

        self.id_cliente = id_cliente
        self.id_proveedor = id_proveedor
        self.id_operador = id_operador
        self.id_rol = id_rol
        self.nombre = nombre
        self.apellido = apellido
        self.email = email
        self.contrasena_encriptada = contrasena_encriptada
        self.estado = estado

    def __str__(self):
        parte = describir_parte(
            self.id_cliente, self.id_proveedor, self.id_operador
        )
        return (
            f"Parte: {parte}\n"
            f"Rol ID: {self.id_rol}\n"
            f"Nombre: {self.nombre}\n"
            f"Apellido: {self.apellido}\n"
            f"Email: {self.email}\n"
            f"Estado: {self.estado}"
        )
