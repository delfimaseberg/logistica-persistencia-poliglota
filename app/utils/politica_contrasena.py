"""Política de contraseñas y parámetros de seguridad del inicio de sesión.

La política se aplica solo cuando se crea, cambia o restablece una contraseña.
Las contraseñas ya guardadas no se revalidan: los usuarios existentes siguen
entrando con la suya.
"""

import re
import unicodedata

LARGO_MINIMO = 8  # largo mínimo de la contraseña
LARGO_MAXIMO = 128            # evita entradas enormes al calcular el hash
LARGO_MINIMO_DATO_PERSONAL = 3  # partes del nombre o email más cortas que esto no se controlan

INTENTOS_MAXIMOS = 5          # intentos fallidos seguidos antes de bloquear
MINUTOS_BLOQUEO = 15  # minutos que queda bloqueado el usuario
MINUTOS_INACTIVIDAD = 30      # cierre de sesión por inactividad
SEGUNDOS_ENTRE_REGISTROS_DE_ACTIVIDAD = 60  # cada cuánto se actualiza la última actividad de la sesión


def _normalizar(texto):  # sin acentos ni mayúsculas, para comparar
    texto = unicodedata.normalize("NFKD", str(texto or ""))
    return "".join(c for c in texto if not unicodedata.combining(c)).casefold()


def _datos_personales(email, nombre, apellido):  # palabras prohibidas; la usa errores_politica
    """Partes del email, nombre y apellido que la contraseña no puede contener."""
    partes = set()
    local = _normalizar(email).split("@", 1)[0]
    if local:
        partes.add(local)
        partes.update(re.split(r"[._+\-]+", local))
    for valor in (nombre, apellido):
        partes.update(re.split(r"[\s\-']+", _normalizar(valor)))
    return {p for p in partes if len(p) >= LARGO_MINIMO_DATO_PERSONAL}


def errores_politica(contrasena, email="", nombre="", apellido=""):  # reglas que no cumple; la usan pedir_contrasena_nueva y validar_politica
    """Lista de reglas que no cumple (vacía si es válida)."""
    contrasena = contrasena or ""
    errores = []
    if len(contrasena) < LARGO_MINIMO:
        errores.append(f"tener al menos {LARGO_MINIMO} caracteres")
    if len(contrasena) > LARGO_MAXIMO:
        errores.append(f"tener como máximo {LARGO_MAXIMO} caracteres")
    if not any(c.isupper() for c in contrasena):  # mayúscula, minúscula, número y símbolo
        errores.append("tener al menos una mayúscula")
    if not any(c.islower() for c in contrasena):
        errores.append("tener al menos una minúscula")
    if not any(c.isdigit() for c in contrasena):
        errores.append("tener al menos un número")
    if not any(not c.isalnum() and not c.isspace() for c in contrasena):
        errores.append("tener al menos un símbolo (por ejemplo ! # $ % & * ? @)")
    if any(c.isspace() for c in contrasena):  # no se permiten espacios
        errores.append("no tener espacios")
    normalizada = _normalizar(contrasena)
    # También sin símbolos intercalados ("delfi.na" contiene "delfina").
    solo_letras = re.sub(r"[^0-9a-z]", "", normalizada)
    if any(parte in normalizada or re.sub(r"[^0-9a-z]", "", parte) in solo_letras  # no puede contener el email, nombre ni apellido
           for parte in _datos_personales(email, nombre, apellido)):
        errores.append("no contener tu email, nombre ni apellido")
    return errores


def validar_politica(contrasena, email="", nombre="", apellido=""):  # igual que errores_politica pero lanza ValueError
    """ValueError con todas las reglas incumplidas, en un solo mensaje."""
    errores = errores_politica(contrasena, email, nombre, apellido)
    if errores:
        raise ValueError("La contraseña debe " + "; ".join(errores) + ".")
    return contrasena


def descripcion_politica():  # la política en una frase; la muestra pedir_contrasena_nueva
    return (f"Mínimo {LARGO_MINIMO} caracteres, con mayúscula, minúscula, número y "
            "símbolo, sin espacios y sin tu email, nombre ni apellido.")
