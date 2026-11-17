"""Reglas de alerta (PostgreSQL, tabla regla_alerta, migración 015).

Cada regla es un umbral: variable, límite (MIN o MAX), valor y severidad.
La detección de anomalías y de sensores sin transmisión las lee de acá.
"""

from decimal import Decimal

from app.database.postgres_connection import get_postgres_connection


VARIABLES = {
    # variable: (nombre, unidad, mínimo posible, máximo posible, límites permitidos)
    "temperatura": ("Temperatura", "°C", Decimal("-50"), Decimal("90"), ("MIN", "MAX")),
    "humedad": ("Humedad", "%", Decimal("0"), Decimal("100"), ("MIN", "MAX")),
    "vibracion": ("Vibración", "", Decimal("0"), Decimal("1000"), ("MIN", "MAX")),
    "bateria": ("Batería", "%", Decimal("0"), Decimal("100"), ("MIN", "MAX")),
    "horas_sin_transmision": ("Horas sin transmisión", "h", Decimal("0.01"), Decimal("8760"), ("MAX",)),
    "salto_temperatura": ("Salto brusco de temperatura", "°C", Decimal("0.01"), Decimal("140"), ("MAX",)),
    "lecturas_congeladas": ("Lecturas idénticas seguidas", "lecturas", Decimal("3"), Decimal("100"), ("MAX",)),
}
SEVERIDADES = ("Baja", "Media", "Alta", "Crítica")  # de menor a mayor
ORDEN_SEVERIDAD = {s: i for i, s in enumerate(SEVERIDADES)}  # para elegir la más severa

_COLUMNAS = """id_regla, variable, limite, valor, severidad, activa, descripcion,
               actualizada_en"""


def _dict(fila):  # fila de la tabla a diccionario
    return {
        "id_regla": fila[0], "variable": fila[1], "limite": fila[2],
        "valor": fila[3], "severidad": fila[4], "activa": fila[5],
        "descripcion": fila[6], "actualizada_en": fila[7],
    }


def validar_regla(variable, limite, valor, severidad):  # controla una regla; la usan crear y modificar
    """Valida y normaliza. Devuelve (variable, limite, Decimal, severidad)."""
    if variable not in VARIABLES:
        raise ValueError("Variable inválida.")
    nombre, _, minimo, maximo, limites = VARIABLES[variable]
    limite = str(limite).strip().upper()
    if limite not in limites:
        raise ValueError(f"{nombre}: el límite debe ser {' o '.join(limites)}.")
    if severidad not in SEVERIDADES:
        raise ValueError("Severidad inválida (Baja, Media, Alta o Crítica).")
    try:
        valor = Decimal(str(valor).replace(",", "."))
    except Exception:
        raise ValueError("El valor debe ser numérico.") from None
    if not valor.is_finite() or not minimo <= valor <= maximo:  # el umbral tiene que estar en el rango posible
        raise ValueError(f"{nombre}: el valor debe estar entre {minimo} y {maximo}.")
    if variable == "lecturas_congeladas" and valor != valor.to_integral_value():
        raise ValueError("La cantidad de lecturas debe ser un número entero.")
    if valor != valor.quantize(Decimal("0.01")):
        raise ValueError("El valor admite hasta 2 decimales.")
    return variable, limite, valor, severidad


def listar_reglas(solo_activas=False):  # reglas de PostgreSQL; la usan el menú de reglas y reglas_vigentes
    with get_postgres_connection() as conexion, conexion.cursor() as cursor:
        cursor.execute(f"""
            SELECT {_COLUMNAS} FROM regla_alerta
            WHERE (%s = FALSE OR activa)  -- si se piden solo activas, filtra; si no, trae todas
            ORDER BY variable, limite, valor, id_regla
        """, (solo_activas,))
        return [_dict(f) for f in cursor.fetchall()]


def obtener_regla(id_regla):  # una regla por ID; la usa modificar_regla
    with get_postgres_connection() as conexion, conexion.cursor() as cursor:
        cursor.execute(f"SELECT {_COLUMNAS} FROM regla_alerta WHERE id_regla = %s",
                       (id_regla,))
        fila = cursor.fetchone()
        return _dict(fila) if fila else None


def crear_regla(variable, limite, valor, severidad, descripcion, id_usuario):  # guarda una regla nueva; la usa crear_regla_service
    variable, limite, valor, severidad = validar_regla(variable, limite, valor, severidad)
    with get_postgres_connection() as conexion, conexion.cursor() as cursor:
        cursor.execute("""
            INSERT INTO regla_alerta (variable, limite, valor, severidad,
                                      descripcion, actualizada_por)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id_regla
        """, (variable, limite, valor, severidad,
              (descripcion or "").strip() or None, id_usuario))
        return cursor.fetchone()[0]


def modificar_regla(id_regla, valor, severidad, id_usuario):  # cambia valor y severidad; la usa modificar_regla_service
    regla = obtener_regla(id_regla)
    if regla is None:
        raise ValueError("La regla no existe.")
    _, _, valor, severidad = validar_regla(regla["variable"], regla["limite"], valor, severidad)  # variable y límite no se cambian
    with get_postgres_connection() as conexion, conexion.cursor() as cursor:
        cursor.execute("""
            UPDATE regla_alerta
            SET valor = %s, severidad = %s, actualizada_por = %s,
                actualizada_en = CURRENT_TIMESTAMP
            WHERE id_regla = %s
        """, (valor, severidad, id_usuario, id_regla))
        return cursor.rowcount == 1


def cambiar_estado_regla(id_regla, activa, id_usuario):  # activa o desactiva; la usa cambiar_estado_regla_service
    with get_postgres_connection() as conexion, conexion.cursor() as cursor:
        cursor.execute("""
            UPDATE regla_alerta
            SET activa = %s, actualizada_por = %s, actualizada_en = CURRENT_TIMESTAMP
            WHERE id_regla = %s AND activa <> %s  -- si ya estaba así, no cambia nada
        """, (activa, id_usuario, id_regla, activa))
        return cursor.rowcount == 1


def contar_activas(variable, limite):  # reglas activas de una variable; la usa cambiar_estado_regla_service
    with get_postgres_connection() as conexion, conexion.cursor() as cursor:
        cursor.execute("""SELECT COUNT(*) FROM regla_alerta
                          WHERE variable = %s AND limite = %s AND activa""",
                       (variable, limite))
        return cursor.fetchone()[0]


# ------------------------------------------------------------ uso en detección

def reglas_vigentes():  # reglas activas agrupadas; las usan toda la detección y la simulación de fallas
    """{(variable, limite): [(valor float, severidad, descripción)...]} de las activas."""
    vigentes = {}
    for regla in listar_reglas(solo_activas=True):
        vigentes.setdefault((regla["variable"], regla["limite"]), []).append(
            (float(regla["valor"]), regla["severidad"], regla["descripcion"]))
    return vigentes


def umbral(vigentes, variable, limite, por_defecto=None):  # el umbral que dispara primero; lo usan la detección y la simulación de fallas
    """El umbral menos exigente de una variable (el primero que dispara).

    MAX: el menor valor; MIN: el mayor. Si no hay reglas activas, por_defecto.
    """
    reglas = vigentes.get((variable, limite))
    if not reglas:
        return por_defecto
    valores = [r[0] for r in reglas]
    return min(valores) if limite == "MAX" else max(valores)
