import hashlib
import hmac
import os

ITERACIONES = 600_000


def generar_hash_contrasena(contrasena):
    salt = os.urandom(16)

    hash_bytes = hashlib.pbkdf2_hmac(
        "sha256",
        contrasena.encode("utf-8"),
        salt,
        ITERACIONES
    )

    return (
        f"pbkdf2_sha256${ITERACIONES}$"
        f"{salt.hex()}${hash_bytes.hex()}"
    )


def verificar_contrasena(contrasena, hash_guardado):
    try:
        algoritmo, iteraciones, salt_hex, hash_hex = (
            hash_guardado.split("$")
        )

        if algoritmo != "pbkdf2_sha256":
            return False

        salt = bytes.fromhex(salt_hex)
        hash_original = bytes.fromhex(hash_hex)

        hash_calculado = hashlib.pbkdf2_hmac(
            "sha256",
            contrasena.encode("utf-8"),
            salt,
            int(iteraciones),
            dklen=len(hash_original)
        )

        return hmac.compare_digest(
            hash_calculado,
            hash_original
        )

    except (ValueError, AttributeError, TypeError):
        return False