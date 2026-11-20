from app.models.rol import Rol
from app.repositories.rol_repository import (
    crear_rol,
    listar_roles,
    buscar_rol_por_id,
    modificar_rol,
    eliminar_rol
)
from app.utils.errores import mensaje_error
from app.services.autenticacion import requiere_permiso


def pedir_id_rol():  # pide el ID de un rol; la usan buscar, modificar y eliminar
    while True:
        valor = input("ID del rol: ").strip()

        if valor.isdigit() and int(valor) > 0:
            return int(valor)

        print("Error: el ID debe ser un número entero positivo.")


def pedir_descripcion():  # pide el nombre del rol; la usan alta y modificación
    while True:
        descripcion = input("Descripción: ").strip()

        if descripcion and len(descripcion) <= 255:
            return descripcion

        print("Error: la descripción es obligatoria (hasta 255 caracteres).")


def pedir_nivel_permisos():  # pide el nivel del rol; la usan alta y modificación
    while True:
        valor = input(
            "Nivel de permisos (0 a 5): "
        ).strip()

        if valor.isdigit():
            nivel = int(valor)

            if 0 <= nivel <= 5:  # el nivel va de 0 a 5; 5 es administrador
                return nivel

        print(
            "Error: el nivel de permisos debe ser "
            "un número entre 0 y 5."
        )


def mostrar_rol(rol):  # imprime un rol
    if rol is None:
        print("Rol no encontrado.")
        return

    print(f"""
ID: {rol[0]}
Descripción: {rol[1]}
Nivel de permisos: {rol[2]}
""")


@requiere_permiso(5)
def registrar_rol():  # da de alta un rol; opción 1 del menú de roles
    print("\n--- REGISTRAR ROL ---")

    descripcion = pedir_descripcion()
    nivel_permisos = pedir_nivel_permisos()

    rol = Rol(
        descripcion,
        nivel_permisos
    )

    try:
        id_rol = crear_rol(rol)  # INSERT en PostgreSQL

        print("\nRol registrado correctamente.")
        print(f"ID asignado: {id_rol}")

    except Exception as error:
        print(f"\nError al registrar el rol: {mensaje_error(error)}")

    input("\nPresioná Enter para continuar...")


@requiere_permiso(5)
def listar_roles_service():  # lista los roles; opción 2 del menú de roles
    print("\n--- LISTADO DE ROLES ---")

    try:
        roles = listar_roles()

        if not roles:
            print("No hay roles registrados.")
        else:
            for rol in roles:
                print("-------------------------------")
                mostrar_rol(rol)

    except Exception as error:
        print(f"Error al listar los roles: {mensaje_error(error)}")

    input("\nPresioná Enter para continuar...")


@requiere_permiso(5)
def buscar_rol_service():  # muestra un rol por ID; opción 3 del menú de roles
    print("\n--- BUSCAR ROL ---")

    id_rol = pedir_id_rol()

    try:
        rol = buscar_rol_por_id(id_rol)
        mostrar_rol(rol)

    except Exception as error:
        print(f"Error al buscar el rol: {mensaje_error(error)}")

    input("\nPresioná Enter para continuar...")


@requiere_permiso(5)
def modificar_rol_service():  # cambia nombre y nivel de un rol; opción 4 del menú de roles
    print("\n--- MODIFICAR ROL ---")

    id_rol = pedir_id_rol()

    try:
        rol_actual = buscar_rol_por_id(id_rol)

        if rol_actual is None:
            print("Rol no encontrado.")
            input("\nPresioná Enter para continuar...")
            return

        print("\nRol actual:")
        mostrar_rol(rol_actual)

        print("Ingresá los nuevos datos:")

        descripcion = pedir_descripcion()
        nivel_permisos = pedir_nivel_permisos()

        rol_modificado = Rol(
            descripcion,
            nivel_permisos
        )

        modificado = modificar_rol(
            id_rol,
            rol_modificado
        )

        if modificado:
            print("\nRol modificado correctamente.")
        else:
            print("\nNo se pudo modificar el rol.")

    except Exception as error:
        print(f"\nError al modificar el rol: {mensaje_error(error)}")

    input("\nPresioná Enter para continuar...")


@requiere_permiso(5)
def eliminar_rol_service():  # borra un rol; opción 5 del menú de roles
    print("\n--- ELIMINAR ROL ---")

    id_rol = pedir_id_rol()

    try:
        rol = buscar_rol_por_id(id_rol)

        if rol is None:
            print("Rol no encontrado.")
            input("\nPresioná Enter para continuar...")
            return

        print("\nRol a eliminar:")
        mostrar_rol(rol)

        confirmacion = input(
            "¿Seguro que querés eliminarlo? (S/N): "
        ).strip().upper()

        if confirmacion != "S":
            print("Eliminación cancelada.")
        else:
            eliminado = eliminar_rol(id_rol)  # si hay usuarios con ese rol, la base no deja borrarlo

            if eliminado:
                print("Rol eliminado correctamente.")
            else:
                print("No se pudo eliminar el rol.")

    except Exception as error:
        print(f"\nError al eliminar el rol: {mensaje_error(error)}")

    input("\nPresioná Enter para continuar...")