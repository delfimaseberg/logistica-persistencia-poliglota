"""Tabla de reporte y exportación a CSV y PDF (fpdf2)."""

import csv
import hashlib
import os
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from fpdf import FPDF


ZONA = ZoneInfo("America/Argentina/Buenos_Aires")
# Configurable para ensayos (REPORTES_DIR); por defecto, reportes_generados/.
CARPETA_REPORTES = Path(os.getenv("REPORTES_DIR", "reportes_generados"))


@dataclass
class Tabla:
    titulo: str
    columnas: list
    filas: list = field(default_factory=list)
    # Bases de datos que la alimentan: documentación interna, no se muestra
    # en pantalla ni en los archivos (queda en el README y en el código).
    fuente: str = ""
    notas: list = field(default_factory=list)
    vacio: str = ""                  # mensaje cuando no hay filas


def mensaje_vacio(tabla, cliente=False, periodo=False):
    """'No hay envíos demorados para el cliente elegido en el período elegido.'"""
    mensaje = tabla.vacio or "No hay datos"
    if cliente:
        mensaje += " para el cliente elegido"
    if periodo:
        mensaje += " en el período elegido"
    return mensaje + "."


def texto(valor):
    """Valor de celda legible: fechas en hora argentina, decimales con 2."""
    if valor is None:
        return "-"
    if isinstance(valor, datetime):
        if valor.tzinfo is not None:
            valor = valor.astimezone(ZONA)
        return valor.strftime("%d/%m/%Y %H:%M")
    if isinstance(valor, date):
        return valor.strftime("%d/%m/%Y")
    if isinstance(valor, Decimal):
        # Cantidades (sin decimales en la base) se muestran enteras; los
        # importes (NUMERIC con escala 2) conservan los dos decimales.
        if valor.as_tuple().exponent >= 0:
            return f"{valor:,.0f}"
        return f"{valor:,.2f}"
    if isinstance(valor, float):
        return f"{valor:,.2f}"
    if isinstance(valor, (list, tuple)):
        return ", ".join(texto(v) for v in valor)
    return str(valor)


def imprimir_tabla(tabla, vacio=None):
    """Muestra la tabla en la consola."""
    print(f"\n=== {tabla.titulo} ===")
    if not tabla.filas:
        print(vacio or mensaje_vacio(tabla))
    else:
        celdas = [[texto(v) for v in fila] for fila in tabla.filas]
        anchos = [
            min(40, max(len(str(c)), *(len(f[i]) for f in celdas)))
            for i, c in enumerate(tabla.columnas)
        ]
        print(" | ".join(str(c)[:a].ljust(a) for c, a in zip(tabla.columnas, anchos)))
        print("-+-".join("-" * a for a in anchos))
        for fila in celdas:
            print(" | ".join(v[:a].ljust(a) for v, a in zip(fila, anchos)))
        print(f"({len(tabla.filas)} fila(s))")
    for nota in tabla.notas:
        print(f"Nota: {nota}")


def hash_archivo(ruta):
    sha = hashlib.sha256()
    with open(ruta, "rb") as archivo:
        for bloque in iter(lambda: archivo.read(65536), b""):
            sha.update(bloque)
    return sha.hexdigest()


def escribir_csv(tabla, ruta, encabezado=()):
    """CSV con separador ';' y BOM UTF-8 (se abre bien en Excel en español)."""
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with open(ruta, "w", newline="", encoding="utf-8-sig") as archivo:
        escritor = csv.writer(archivo, delimiter=";")
        for linea in encabezado:
            escritor.writerow([f"# {linea}"])
        escritor.writerow(tabla.columnas)
        for fila in tabla.filas:
            escritor.writerow([texto(v) for v in fila])
    return ruta


def _latin1(valor):
    """Las fuentes estándar del PDF usan Latin-1: acentos y ñ sí; flechas no."""
    return (str(valor).replace("→", "->").replace("—", "-").replace("–", "-")
            .encode("latin-1", "replace").decode("latin-1"))


def escribir_pdf(tabla, ruta, encabezado=()):
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=12)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 8, _latin1(tabla.titulo), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    for linea in encabezado:
        pdf.cell(0, 5, _latin1(linea), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    ancho_total = pdf.w - pdf.l_margin - pdf.r_margin
    celdas = [[texto(v) for v in fila] for fila in tabla.filas]
    pesos = [
        max(4, min(30, max([len(str(c))] + [len(f[i]) for f in celdas])))
        for i, c in enumerate(tabla.columnas)
    ]
    anchos = [ancho_total * p / sum(pesos) for p in pesos]

    def fila_pdf(valores, negrita=False):
        pdf.set_font("Helvetica", "B" if negrita else "", 7.5)
        for valor, ancho in zip(valores, anchos):
            contenido = _latin1(valor)
            while contenido and pdf.get_string_width(contenido) > ancho - 1.5:
                contenido = contenido[:-1]
            pdf.cell(ancho, 5, contenido, border=1)
        pdf.ln(5)

    fila_pdf(tabla.columnas, negrita=True)
    for fila in celdas:
        if pdf.get_y() > pdf.h - 18:
            pdf.add_page()
            fila_pdf(tabla.columnas, negrita=True)
        fila_pdf(fila)
    if not celdas:
        pdf.cell(0, 6, _latin1(mensaje_vacio(tabla)), new_x="LMARGIN", new_y="NEXT")
    for nota in tabla.notas:
        pdf.set_font("Helvetica", "I", 8)
        pdf.multi_cell(0, 4, _latin1(f"Nota: {nota}"), new_x="LMARGIN", new_y="NEXT")
    pdf.output(str(ruta))
    return ruta


def exportar(tabla, formato, ruta_sin_extension, encabezado=()):
    """Escribe CSV o PDF y devuelve (ruta, hash)."""
    formato = str(formato).upper()
    if formato == "CSV":
        ruta = escribir_csv(tabla, f"{ruta_sin_extension}.csv", encabezado)
    elif formato == "PDF":
        ruta = escribir_pdf(tabla, f"{ruta_sin_extension}.pdf", encabezado)
    else:
        raise ValueError("Formato inválido (CSV o PDF).")
    return ruta, hash_archivo(ruta)
