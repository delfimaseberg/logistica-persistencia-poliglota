"""Regenera los hashes de los usuarios de ejemplo (Lucía, Diego, Paula y Sofía)
para que cada uno tenga su propia sal, y confirma que los 5 usuarios de
ejemplo (con Delfina) inician sesión.

- La contraseña se pide por teclado (oculta) y nunca se guarda ni se muestra.
- Antes de cambiar nada verifica que la contraseña coincida con el hash actual
  de los cuatro usuarios; si no coincide, no toca nada.
- No marca "debe cambiar contraseña" y no cambia la contraseña: solo el hash.
- Sin --aplicar solo verifica (no escribe).
- Al final hace un inicio de sesión real de cada usuario y lo cierra.

Uso (desde la carpeta del proyecto, con respaldo previo de PostgreSQL):
    .venv\\Scripts\\python.exe scripts\\datos_demo\\regenerar_hashes_demo.py            # verificar
    .venv\\Scripts\\python.exe scripts\\datos_demo\\regenerar_hashes_demo.py --aplicar  # regenerar
"""

import contextlib
import io
import os
import sys
from getpass import getpass
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.database.postgres_connection import get_postgres_connection  # noqa: E402
from app.utils.seguridad import generar_hash_contrasena, verificar_contrasena  # noqa: E402

DEMO = {5: "Lucía", 6: "Diego", 7: "Paula", 8: "Sofía"}
INTERNA = {4: "Delfina"}


def _base():
    with get_postgres_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT current_database()")
        return cur.fetchone()[0]


def _usuarios():
    with get_postgres_connection() as conn, conn.cursor() as cur:
        cur.execute("""SELECT id_usuario, email, contrasena_encriptada
                       FROM usuario WHERE id_usuario = ANY(%s)""",
                    (list(DEMO) + list(INTERNA),))
        return {fila[0]: fila[1:] for fila in cur.fetchall()}


def regenerar(clave, usuarios, aplicar):
    """Verifica la clave contra los 4 hashes y, con aplicar, guarda uno nuevo por usuario."""
    no_coinciden = [DEMO[i] for i in DEMO if not verificar_contrasena(clave, usuarios[i][1])]
    if no_coinciden:
        print("La contraseña no coincide con el hash actual de: " + ", ".join(no_coinciden)
              + ". No se cambió nada.")
        return False
    print("La contraseña coincide con el hash actual de los 4 usuarios de ejemplo.")
    if not aplicar:
        print("Verificación sin cambios (para regenerar, agregá --aplicar).")
        return True
    nuevos = {i: generar_hash_contrasena(clave) for i in DEMO}
    sales = {h.split("$")[2] for h in nuevos.values()}
    if len(sales) != len(DEMO) or not all(verificar_contrasena(clave, h) for h in nuevos.values()):
        print("Los hashes nuevos no son válidos o comparten sal. No se cambió nada.")
        return False
    with get_postgres_connection() as conn, conn.cursor() as cur:
        for i, nuevo in nuevos.items():
            # Se reemplaza solo si el hash sigue siendo el verificado (nadie lo cambió).
            cur.execute("""UPDATE usuario
                           SET contrasena_encriptada = %s, contrasena_actualizada_en = now()
                           WHERE id_usuario = %s AND contrasena_encriptada = %s""",
                        (nuevo, i, usuarios[i][1]))
            if cur.rowcount != 1:
                conn.rollback()
                print(f"El hash de {DEMO[i]} cambió mientras tanto. No se cambió nada.")
                return False
        cur.execute("""SELECT count(DISTINCT split_part(contrasena_encriptada, '$', 3))
                       FROM usuario WHERE id_usuario = ANY(%s)""", (list(DEMO),))
        if cur.fetchone()[0] != len(DEMO):
            conn.rollback()
            print("Las sales no quedaron distintas. No se cambió nada.")
            return False
    print("Hashes regenerados: cada usuario de ejemplo tiene su propia sal.")
    return True


def iniciar_sesion(email, clave):
    """Inicio de sesión real (el mismo del menú) y cierre. Devuelve True si entró."""
    from app.services import autenticacion, sesion_service
    salida = io.StringIO()
    with patch("builtins.input", return_value=email), \
            patch.object(sesion_service, "getpass", return_value=clave), \
            contextlib.redirect_stdout(salida):
        entro = sesion_service.iniciar_sesion_service()
        sesion = autenticacion.obtener_sesion_actual()
        entro = bool(entro and sesion and sesion["email"].lower() == email.lower())
        if sesion:
            sesion_service.cerrar_sesion_service()
    autenticacion.limpiar_sesion()
    return entro


def confirmar_ingresos(usuarios, clave_demo, clave_interna):
    """Solo intenta entrar si la clave verifica (así no suma intentos fallidos)."""
    resultados = {}
    for i, nombre in {**INTERNA, **DEMO}.items():
        clave = clave_interna if i in INTERNA else clave_demo
        email, hash_actual = _usuarios()[i]
        if not verificar_contrasena(clave, hash_actual):
            resultados[nombre] = "NO ENTRA (la contraseña no coincide; no se intentó)"
            continue
        resultados[nombre] = "inicia sesión correctamente" if iniciar_sesion(email, clave) \
            else "NO ENTRA"
    for nombre, resultado in resultados.items():
        print(f"  {nombre}: {resultado}")
    return all(r == "inicia sesión correctamente" for r in resultados.values())


def main(argv=None, pedir=getpass):
    argv = sys.argv[1:] if argv is None else argv
    aplicar = "--aplicar" in argv
    base = _base()
    print(f"Base: {base}")
    esperada = os.getenv("BASE_ESPERADA", "logistica_poliglota")
    if base != esperada:
        print(f"La base no es {esperada}. No se hace nada.")
        return 2
    usuarios = _usuarios()
    if set(usuarios) != set(DEMO) | set(INTERNA):
        print("Faltan usuarios de ejemplo en la base. No se hace nada.")
        return 2
    clave_demo = pedir("Contraseña de los usuarios de ejemplo (Lucía, Diego, Paula, Sofía): ")
    if not regenerar(clave_demo, usuarios, aplicar):
        return 1
    clave_interna = pedir("Contraseña de Delfina (Enter = la misma): ") or clave_demo
    print("\nInicio de sesión de los 5 usuarios:")
    ok = confirmar_ingresos(usuarios, clave_demo, clave_interna)
    del clave_demo, clave_interna
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
