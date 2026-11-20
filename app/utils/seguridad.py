import hashlib
import hmac
import os

ITERACIONES = 600_000  # vueltas de PBKDF2: más vueltas, más lento probar contraseñas por fuerza bruta


def generar_hash_contrasena(contrasena):  # arma el hash para guardar; la usan el alta de usuarios y el cambio de contraseña
    salt = os.urandom(16)  # sal al azar distinta para cada contraseña

    hash_bytes = hashlib.pbkdf2_hmac(  # PBKDF2 con SHA-256
        "sha256",
        contrasena.encode("utf-8"),
        salt,
        ITERACIONES
    )

    return (
        f"pbkdf2_sha256${ITERACIONES}$"  # se guarda algoritmo, iteraciones, sal y hash separados por $
        f"{salt.hex()}${hash_bytes.hex()}"
    )


def verificar_contrasena(contrasena, hash_guardado):  # compara una contraseña con el hash guardado; la usan el inicio de sesión y el cambio de contraseña
    try:
        algoritmo, iteraciones, salt_hex, hash_hex = (
            hash_guardado.split("$")
        )

        if algoritmo != "pbkdf2_sha256":
            return False

        salt = bytes.fromhex(salt_hex)
        hash_original = bytes.fromhex(hash_hex)

        hash_calculado = hashlib.pbkdf2_hmac(  # repite el cálculo con la misma sal e iteraciones
            "sha256",
            contrasena.encode("utf-8"),
            salt,
            int(iteraciones),
            dklen=len(hash_original)
        )

        return hmac.compare_digest(  # compara en tiempo constante
            hash_calculado,
            hash_original
        )

    except (ValueError, AttributeError, TypeError):
        return False