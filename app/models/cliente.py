class Cliente:
    def __init__(self, razon_social, cuit, email, telefono, direccion, pais, estado):
        self.razon_social = razon_social
        self.cuit = cuit
        self.email = email
        self.telefono = telefono
        self.direccion = direccion
        self.pais = pais
        self.estado = estado

    def __str__(self):
        return (
            f"Razón social: {self.razon_social}\n"
            f"CUIT: {self.cuit}\n"
            f"Email: {self.email}\n"
            f"Teléfono: {self.telefono}\n"
            f"Dirección: {self.direccion}\n"
            f"País: {self.pais}\n"
            f"Estado: {self.estado}"
        )