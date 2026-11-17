from app.database.postgres_connection import get_postgres_connection
from app.utils.politica_contrasena import (
    INTENTOS_MAXIMOS,
    MINUTOS_BLOQUEO,
    MINUTOS_INACTIVIDAD,
)


def buscar_usuario_por_email(email):  # datos para iniciar sesión; la usa iniciar_sesion_service
    """Datos para iniciar sesión, o None.

    (id, nombre, apellido, email, hash, estado, rol, nivel,
     bloqueado, minutos_de_bloqueo_restantes, debe_cambiar_contrasena)
    El bloqueo se calcula con la hora de la base (bloqueado_hasta > now()).
    """
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    u.id_usuario,
                    u.nombre,
                    u.apellido,
                    u.email,
                    u.contrasena_encriptada,
                    u.estado,
                    r.descripcion,
                    r.nivel_permisos,
                    COALESCE(u.bloqueado_hasta > now(), FALSE) AS bloqueado,  -- bloqueado si el plazo no venció
                    GREATEST(1, CEIL(EXTRACT(EPOCH FROM (u.bloqueado_hasta - now())) / 60))::int  -- minutos que faltan, redondeado para arriba
                        AS minutos_restantes,
                    u.debe_cambiar_contrasena
                FROM usuario u
                JOIN rol r
                    ON u.id_rol = r.id_rol
                WHERE LOWER(u.email) = LOWER(%s);  -- sin distinguir mayúsculas
                """,
                (email,)
            )

            return cursor.fetchone()


def registrar_intento_fallido(id_usuario):  # suma un intento y bloquea al llegar al máximo; la usan el inicio de sesión y cambiar mi contraseña
    """Suma un intento fallido; al llegar al máximo bloquea al usuario.

    Si el bloqueo anterior ya venció, la cuenta empieza de nuevo.
    Devuelve (intentos, bloqueado_ahora).
    """
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                UPDATE usuario
                SET intentos_fallidos = CASE
                        WHEN bloqueado_hasta IS NOT NULL AND bloqueado_hasta <= now()  -- si el bloqueo anterior ya venció, vuelve a 1
                            THEN 1 ELSE intentos_fallidos + 1 END,
                    bloqueado_hasta = CASE
                        WHEN (CASE WHEN bloqueado_hasta IS NOT NULL AND bloqueado_hasta <= now()
                                   THEN 1 ELSE intentos_fallidos + 1 END) >= %s  -- llegó al máximo de intentos...
                            THEN now() + make_interval(mins => %s)  -- ...bloqueado por los minutos de bloqueo
                        ELSE NULL END
                WHERE id_usuario = %s
                RETURNING intentos_fallidos, bloqueado_hasta IS NOT NULL;
                """,
                (INTENTOS_MAXIMOS, MINUTOS_BLOQUEO, id_usuario)
            )
            fila = cursor.fetchone()
            return (fila[0], bool(fila[1])) if fila else (0, False)


def registrar_ingreso_correcto(id_usuario):  # vuelve a cero los intentos; la usa iniciar_sesion_service
    """Vuelve a cero los intentos fallidos y quita el bloqueo vencido."""
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                UPDATE usuario
                SET intentos_fallidos = 0, bloqueado_hasta = NULL
                WHERE id_usuario = %s
                  AND (intentos_fallidos <> 0 OR bloqueado_hasta IS NOT NULL);
                """,
                (id_usuario,)
            )


def iniciar_sesion_db(id_usuario):  # crea la sesión ACTIVA; la usa iniciar_sesion_service
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO sesion (
                    id_usuario,
                    estado
                )
                SELECT
                    id_usuario,
                    'ACTIVA'
                FROM usuario
                WHERE id_usuario = %s
                  AND estado = 'ACTIVO'  -- solo si el usuario está activo
                RETURNING id_sesion;
                """,
                (id_usuario,)
            )

            resultado = cursor.fetchone()

            if resultado is None:
                return None

            return resultado[0]


def expirar_sesiones_inactivas():  # cierra por inactividad; la usa la opción 7 del menú de usuarios
    """Cierra (EXPIRADA) las sesiones sin actividad en los últimos minutos.

    La fecha de fin es la de la última actividad más el plazo de inactividad.
    Devuelve la cantidad de sesiones cerradas.
    """
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                UPDATE sesion
                SET estado = 'EXPIRADA',
                    fecha_fin = GREATEST(
                        fecha_inicio,
                        LEAST(now(), ultima_actividad + make_interval(mins => %s)))  -- el fin es la última actividad más el plazo
                WHERE estado = 'ACTIVA'
                  AND fecha_fin IS NULL
                  AND ultima_actividad < now() - make_interval(mins => %s);  -- sin actividad en los últimos 30 minutos
                """,
                (MINUTOS_INACTIVIDAD, MINUTOS_INACTIVIDAD)
            )
            return cursor.rowcount


def listar_sesiones_activas():  # sesiones abiertas con su usuario; la usa la opción 7 del menú de usuarios
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    s.id_sesion,
                    u.id_usuario,
                    u.nombre,
                    u.apellido,
                    u.email,
                    s.fecha_inicio,
                    CASE  -- a qué parte pertenece el usuario
                        WHEN u.id_cliente IS NOT NULL
                            THEN 'Cliente: ' || c.razon_social
                        WHEN u.id_proveedor IS NOT NULL
                            THEN 'Proveedor: ' || p.razon_social
                        WHEN u.id_operador IS NOT NULL
                            THEN 'Operador: ' || o.razon_social
                        ELSE 'Interno'
                    END AS parte,
                    s.ultima_actividad
                FROM sesion s
                JOIN usuario u
                    ON s.id_usuario = u.id_usuario
                LEFT JOIN cliente c ON c.id_cliente = u.id_cliente
                LEFT JOIN proveedor p ON p.id_proveedor = u.id_proveedor
                LEFT JOIN operador_logistico o ON o.id_operador = u.id_operador
                WHERE s.estado = 'ACTIVA'
                  AND s.fecha_fin IS NULL
                ORDER BY s.fecha_inicio DESC;
                """
            )

            return cursor.fetchall()


def listar_usuarios_bloqueados():  # bloqueos vigentes; la usan sesiones activas y desbloquear usuario
    """(id, nombre, apellido, email, bloqueado_hasta) de los bloqueos vigentes."""
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                SELECT id_usuario, nombre, apellido, email, bloqueado_hasta
                FROM usuario
                WHERE bloqueado_hasta > now()
                ORDER BY bloqueado_hasta;
                """
            )
            return cursor.fetchall()


def cerrar_sesion_db(id_sesion, id_usuario):  # cierra la propia sesión; la usan cerrar sesión y los cierres forzados
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                UPDATE sesion
                SET
                    estado = 'CERRADA',
                    fecha_fin = CURRENT_TIMESTAMP
                WHERE id_sesion = %s
                  AND id_usuario = %s
                  AND estado = 'ACTIVA'
                  AND fecha_fin IS NULL;
                """,
                (id_sesion, id_usuario)
            )

            return cursor.rowcount > 0

def cerrar_sesion_ajena_db(id_sesion, id_administrador):  # la usa cerrar_sesion_de_otro
    """Un administrador cierra la sesión activa de OTRO usuario.

    Queda registrado quién la cerró (sesion.cerrada_por, migración 015).
    """
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                UPDATE sesion
                SET
                    estado = 'CERRADA',
                    fecha_fin = CURRENT_TIMESTAMP,
                    cerrada_por = %s
                WHERE id_sesion = %s
                  AND id_usuario <> %s  -- no puede ser la del propio administrador
                  AND estado = 'ACTIVA'
                  AND fecha_fin IS NULL;
                """,
                (id_administrador, id_sesion, id_administrador)
            )

            return cursor.rowcount > 0


def cerrar_sesiones_de_usuario(id_usuario, cerrada_por, excepto_sesion=None):  # cierra todas las sesiones de un usuario; la usa guardar_contrasena
    """Cierra las sesiones activas de un usuario (cambio o reseteo de contraseña)."""
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                UPDATE sesion
                SET estado = 'CERRADA', fecha_fin = CURRENT_TIMESTAMP, cerrada_por = %s
                WHERE id_usuario = %s AND estado = 'ACTIVA' AND fecha_fin IS NULL
                  AND (%s::bigint IS NULL OR id_sesion <> %s::bigint);  -- menos la que se quiere conservar
                """,
                (cerrada_por, id_usuario, excepto_sesion, excepto_sesion)
            )
            return cursor.rowcount


def cerrada_por_otro(id_sesion):  # si la sesión la cerró otro usuario
    """True si la sesión la cerró un usuario distinto de su dueño."""
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute(
                "SELECT cerrada_por, id_usuario FROM sesion WHERE id_sesion = %s",
                (id_sesion,)
            )
            fila = cursor.fetchone()
            return bool(fila and fila[0] is not None and fila[0] != fila[1])


def motivo_cierre(id_sesion):  # por qué se cerró la sesión; la usa obtener_sesion_actual para el aviso
    """'INACTIVIDAD', 'ADMINISTRADOR' o None (la cerró el propio usuario)."""
    with get_postgres_connection() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute(
                "SELECT estado, cerrada_por, id_usuario FROM sesion WHERE id_sesion = %s",
                (id_sesion,)
            )
            fila = cursor.fetchone()
    if not fila:
        return None
    if fila[0] == "EXPIRADA":
        return "INACTIVIDAD"
    if fila[1] is not None and fila[1] != fila[2]:
        return "ADMINISTRADOR"
    return None
