"""ABM de proveedores y operadores logísticos (PostgreSQL).

La baja es lógica: estado INACTIVO + fecha_baja. Nunca se borran filas,
porque las facturas, pagos, tramos y usuarios pueden referenciarlas.
"""

from psycopg import errors

from app.database.postgres_connection import get_postgres_connection
from app.utils.validaciones_datos import validar_contacto


COLUMNAS_COMUNES = (
    "razon_social, cuit, email, telefono, direccion, pais"
)

COLUMNAS_PROVEEDOR = (
    f"id_proveedor, {COLUMNAS_COMUNES}, rubro, estado, fecha_alta, fecha_baja"
)
COLUMNAS_OPERADOR = (
    f"id_operador, {COLUMNAS_COMUNES}, modalidades, estado, fecha_alta, fecha_baja"
)

# Configuración por tipo. Los nombres vienen de esta tabla fija, nunca del
# usuario, así que es seguro interpolarlos en el SQL.
_TIPOS = {
    "PROVEEDOR": {
        "tabla": "proveedor",
        "id": "id_proveedor",
        "columnas": COLUMNAS_PROVEEDOR,
        "extra": "rubro",
        "nombre": "proveedor",
    },
    "OPERADOR": {
        "tabla": "operador_logistico",
        "id": "id_operador",
        "columnas": COLUMNAS_OPERADOR,
        "extra": "modalidades",
        "nombre": "operador logístico",
    },
}


def _config(tipo):  # configuración del tipo; falla si no es PROVEEDOR ni OPERADOR
    try:
        return _TIPOS[tipo]
    except KeyError:
        raise ValueError("Tipo de tercero inválido.") from None


def _validar(datos):
    """CUIT con dígito verificador, email, teléfono y largos de las columnas."""
    return validar_contacto(datos)


def _repetido(error, c, otro=False):  # arma el error de CUIT o email repetido según la restricción que falló
    restriccion = getattr(getattr(error, "diag", None), "constraint_name", "") or ""
    articulo = "otro" if otro else "un"
    dato = "email" if "email" in restriccion else "CUIT"
    return ValueError(f"Ya existe {articulo} {c['nombre']} con ese {dato}.")


def _crear(tipo, datos):  # alta de proveedor u operador; devuelve el ID nuevo
    c = _config(tipo)
    datos = _validar(datos)
    try:
        with get_postgres_connection() as conexion:
            with conexion.cursor() as cursor:
                cursor.execute(f"""
                    INSERT INTO {c['tabla']} (
                        razon_social, cuit, email, telefono, direccion,
                        pais, {c['extra']}, estado
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, 'ACTIVO')  -- todo tercero nuevo empieza activo
                    RETURNING {c['id']}
                """, (
                    datos["razon_social"], datos["cuit"], datos["email"],
                    datos.get("telefono"), datos.get("direccion"),
                    datos["pais"], datos[c["extra"]],
                ))
                return cursor.fetchone()[0]
    except errors.UniqueViolation as error:  # CUIT o email ya usados por otro registro
        raise _repetido(error, c) from None


def _listar(tipo, incluir_inactivos=True):  # proveedores u operadores, con o sin los inactivos
    c = _config(tipo)
    filtro = "" if incluir_inactivos else "WHERE estado = 'ACTIVO'"
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute(f"""
                SELECT {c['columnas']}
                FROM {c['tabla']}
                {filtro}
                ORDER BY razon_social, {c['id']}
            """)
            return cursor.fetchall()


def _buscar(tipo, id_tercero):  # un tercero por ID, o None
    c = _config(tipo)
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute(f"""
                SELECT {c['columnas']}
                FROM {c['tabla']}
                WHERE {c['id']} = %s
            """, (id_tercero,))
            return cursor.fetchone()


def _buscar_por_cuit(tipo, cuit):  # un tercero por CUIT; sirve para no repetir CUIT en alta y modificación
    c = _config(tipo)
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute(f"""
                SELECT {c['columnas']}
                FROM {c['tabla']}
                WHERE cuit = %s
            """, (cuit,))
            return cursor.fetchone()


def _modificar(tipo, id_tercero, datos):  # actualiza los datos de un tercero; devuelve True si existía
    c = _config(tipo)
    datos = _validar(datos)
    try:
        with get_postgres_connection() as conexion:
            with conexion.cursor() as cursor:
                cursor.execute(f"""
                    UPDATE {c['tabla']}
                    SET razon_social = %s, cuit = %s, email = %s,
                        telefono = %s, direccion = %s, pais = %s,
                        {c['extra']} = %s
                    WHERE {c['id']} = %s
                """, (
                    datos["razon_social"], datos["cuit"], datos["email"],
                    datos.get("telefono"), datos.get("direccion"),
                    datos["pais"], datos[c["extra"]], id_tercero,
                ))
                return cursor.rowcount == 1
    except errors.UniqueViolation as error:
        raise _repetido(error, c, otro=True) from None


def _dar_de_baja(tipo, id_tercero):
    """Baja lógica. Devuelve False si no existe o ya estaba inactivo."""
    c = _config(tipo)
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute(f"""
                UPDATE {c['tabla']}
                SET estado = 'INACTIVO', fecha_baja = CURRENT_TIMESTAMP
                WHERE {c['id']} = %s AND estado = 'ACTIVO'
            """, (id_tercero,))
            return cursor.rowcount == 1


def _reactivar(tipo, id_tercero):  # vuelve a ACTIVO un tercero dado de baja y limpia la fecha de baja
    c = _config(tipo)
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute(f"""
                UPDATE {c['tabla']}
                SET estado = 'ACTIVO', fecha_baja = NULL
                WHERE {c['id']} = %s AND estado = 'INACTIVO'
            """, (id_tercero,))
            return cursor.rowcount == 1


# ---------------------------------------------------------------- Proveedores

def crear_proveedor(datos):  
    return _crear("PROVEEDOR", datos)


def listar_proveedores(incluir_inactivos=True):  # todos los proveedores o solo los activos
    return _listar("PROVEEDOR", incluir_inactivos)


def buscar_proveedor(id_proveedor):  
    return _buscar("PROVEEDOR", id_proveedor)


def buscar_proveedor_por_cuit(cuit):  
    return _buscar_por_cuit("PROVEEDOR", cuit)


def modificar_proveedor(id_proveedor, datos):  
    return _modificar("PROVEEDOR", id_proveedor, datos)


def dar_de_baja_proveedor(id_proveedor):  
    return _dar_de_baja("PROVEEDOR", id_proveedor)


def reactivar_proveedor(id_proveedor):  
    return _reactivar("PROVEEDOR", id_proveedor)


# ------------------------------------------------------------------ Operadores

def crear_operador(datos):  
    return _crear("OPERADOR", datos)


def listar_operadores(incluir_inactivos=True):  
    return _listar("OPERADOR", incluir_inactivos)


def buscar_operador(id_operador):  
    return _buscar("OPERADOR", id_operador)


def buscar_operador_por_cuit(cuit):  
    return _buscar_por_cuit("OPERADOR", cuit)


def modificar_operador(id_operador, datos):  
    return _modificar("OPERADOR", id_operador, datos)


def dar_de_baja_operador(id_operador):  
    return _dar_de_baja("OPERADOR", id_operador)


def reactivar_operador(id_operador):  
    return _reactivar("OPERADOR", id_operador)


def listar_operadores_por_modalidad(modalidad):
    """Operadores ACTIVOS que tienen la modalidad indicada."""
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute(f"""
                SELECT {COLUMNAS_OPERADOR}
                FROM operador_logistico
                WHERE estado = 'ACTIVO' AND %s = ANY (modalidades)  -- la modalidad tiene que estar en el arreglo de modalidades del operador
                ORDER BY razon_social, id_operador
            """, (modalidad,))
            return cursor.fetchall()


def asignar_operador_vehiculo(id_vehiculo, id_operador):
    """Asigna (o quita, con None) el operador de un vehículo.

    El operador debe estar activo y tener la modalidad del vehículo.
    """
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT tipo FROM vehiculo WHERE id_vehiculo = %s FOR UPDATE  -- bloquea el vehículo hasta terminar la asignación
            """, (id_vehiculo,))
            vehiculo = cursor.fetchone()
            if vehiculo is None:
                raise ValueError("El vehículo no existe.")

            if id_operador is not None:
                cursor.execute("""
                    SELECT estado, modalidades
                    FROM operador_logistico
                    WHERE id_operador = %s
                    FOR SHARE  -- que no den de baja al operador mientras se asigna
                """, (id_operador,))
                operador = cursor.fetchone()
                if operador is None:
                    raise ValueError("El operador no existe.")
                if operador[0] != "ACTIVO":
                    raise ValueError("El operador está inactivo.")
                if vehiculo[0] not in (operador[1] or []):
                    raise ValueError(
                        f"El operador no tiene la modalidad {vehiculo[0]} "
                        "del vehículo."
                    )

            cursor.execute("""
                UPDATE vehiculo SET id_operador = %s WHERE id_vehiculo = %s
            """, (id_operador, id_vehiculo))
            return cursor.rowcount == 1


def asignar_operador_tramo(id_tramo, id_operador):
    """Asigna operador a un tramo que todavía no tiene.

    No reemplaza un operador ya asignado: el tramo registra quién lo hizo.
    Devuelve el id_envio del tramo, para sincronizar Neo4j.
    """
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT id_envio, medio_transporte, id_operador
                FROM tramo
                WHERE id_tramo = %s
                FOR UPDATE  -- evita que dos usuarios asignen operador al mismo tramo a la vez
            """, (id_tramo,))
            tramo = cursor.fetchone()
            if tramo is None:
                raise ValueError("El tramo no existe.")
            id_envio, medio, actual = tramo
            if actual is not None:
                raise ValueError("El tramo ya tiene un operador asignado.")

            cursor.execute("""
                SELECT estado, modalidades
                FROM operador_logistico
                WHERE id_operador = %s
                FOR SHARE
            """, (id_operador,))
            operador = cursor.fetchone()
            if operador is None:
                raise ValueError("El operador no existe.")
            if operador[0] != "ACTIVO":
                raise ValueError("El operador está inactivo.")
            if medio not in (operador[1] or []):
                raise ValueError(
                    f"El operador no tiene la modalidad {medio} del tramo."
                )

            cursor.execute("""
                UPDATE tramo SET id_operador = %s
                WHERE id_tramo = %s AND id_operador IS NULL  -- solo si el tramo sigue sin operador
            """, (id_operador, id_tramo))
            if cursor.rowcount != 1:
                raise ValueError("No se pudo asignar el operador al tramo.")
            return id_envio


def listar_tramos_operador(id_operador):  # tramos que hizo el operador, con el estado del envío y si ya se facturaron; la usa tramos realizados por un operador
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT t.id_tramo, t.id_envio, t.medio_transporte,
                       t.origen, t.destino, t.fecha_salida,
                       t.fecha_estimada_llegada, e.estado,
                       EXISTS (
                           SELECT 1 FROM factura_recibida fr
                           WHERE fr.id_tramo = t.id_tramo
                             AND fr.estado <> 'Anulada'  -- una factura anulada no cuenta
                       ) AS facturado
                FROM tramo t
                JOIN envio e ON e.id_envio = t.id_envio
                WHERE t.id_operador = %s
                ORDER BY t.fecha_salida, t.id_tramo
            """, (id_operador,))
            return cursor.fetchall()


def listar_tramos_sin_operador():  # tramos que todavía no tienen operador; la usa asignar operador a un tramo
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT t.id_tramo, t.id_envio, t.medio_transporte,
                       t.origen, t.destino, t.fecha_salida,
                       v.identificacion, v.empresa_operadora  -- texto histórico del operador, solo para mostrar
                FROM tramo t
                JOIN vehiculo v ON v.id_vehiculo = t.id_vehiculo
                WHERE t.id_operador IS NULL
                ORDER BY t.id_tramo
            """)
            return cursor.fetchall()
