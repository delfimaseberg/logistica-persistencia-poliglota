from app.models.cliente import Cliente
from app.repositories.cliente_repository import (
    crear_cliente,
    listar_clientes,
    buscar_cliente_por_id,
    modificar_cliente,
    eliminar_cliente
)


cliente_prueba = Cliente(
    razon_social="Cliente Prueba TP",
    cuit="20-12345678-9",
    email="prueba@tp.com",
    telefono="1122334455",
    direccion="Dirección de prueba 123",
    pais="Argentina",
    estado="ACTIVO"
)


print("\n1. CREAR CLIENTE")

id_cliente = crear_cliente(cliente_prueba)

print(f"Cliente creado con ID: {id_cliente}")


print("\n2. LISTAR CLIENTES")

clientes = listar_clientes()

for cliente in clientes:
    print(cliente)


print("\n3. BUSCAR CLIENTE")

cliente = buscar_cliente_por_id(id_cliente)

print(cliente)


print("\n4. MODIFICAR CLIENTE")

cliente_prueba.telefono = "1199999999"

modificado = modificar_cliente(
    id_cliente,
    cliente_prueba
)

print(f"Cliente modificado: {modificado}")


print("\n5. VERIFICAR MODIFICACIÓN")

cliente = buscar_cliente_por_id(id_cliente)

print(cliente)


print("\n6. ELIMINAR CLIENTE")

eliminado = eliminar_cliente(id_cliente)

print(f"Cliente eliminado: {eliminado}")


print("\n7. VERIFICAR ELIMINACIÓN")

cliente = buscar_cliente_por_id(id_cliente)

print(cliente)