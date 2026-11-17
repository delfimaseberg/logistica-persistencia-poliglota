"""Tabla de reporte y exportación a CSV y PDF (fpdf2)."""

import csv  # para escribir los CSV
import hashlib  # para el hash SHA-256 del archivo generado
import os
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from fpdf import FPDF  # librería que arma los PDF

from app.utils import formato  # fechas y números en formato argentino


ZONA = ZoneInfo("America/Argentina/Buenos_Aires")  # zona horaria para mostrar las fechas
# Configurable para ensayos (REPORTES_DIR); por defecto, reportes_generados/.
CARPETA_REPORTES = Path(os.getenv("REPORTES_DIR", "reportes_generados"))  # carpeta donde se guardan los archivos; la usan los reportes cobrables y la exportación a CSV


@dataclass  # genera solo el constructor con estos campos
class Tabla:  # resultado de cualquier reporte: lo que devuelven todas las funciones de reportes_service
    titulo: str  # título que se muestra arriba de la tabla
    columnas: list  # nombres de las columnas, en orden
    filas: list = field(default_factory=list)  # una tupla por fila, con los valores en el orden de columnas
    # Bases de datos que la alimentan: documentación interna, no se muestra
    # en pantalla ni en los archivos (queda en el README y en el código).
    fuente: str = ""  # de qué bases salen los datos (no se muestra)
    notas: list = field(default_factory=list)  # aclaraciones que se imprimen debajo de la tabla
    vacio: str = ""                  # mensaje cuando no hay filas


def mensaje_vacio(tabla, cliente=False, periodo=False):  # arma el mensaje de 'no hay datos'; lo usan imprimir_tabla, el PDF y _ejecutar
    """'No hay envíos demorados para el cliente elegido en el período elegido.'"""
    mensaje = tabla.vacio or "No hay datos"  # el mensaje propio del reporte o uno genérico
    if cliente:  # si se filtró por cliente, lo aclara
        mensaje += " para el cliente elegido"
    if periodo:  # si se filtró por período, también
        mensaje += " en el período elegido"
    return mensaje + "."


def texto(valor):  # convierte un valor de celda en texto legible; la usan la pantalla, el CSV y el PDF de todos los reportes
    """Valor de celda legible: fechas en hora argentina, decimales con 2."""
    if valor is None:  # lo vacío se muestra como guion
        return "-"
    if isinstance(valor, datetime):  # fechas con hora
        if valor.tzinfo is None:  # sin zona horaria se muestra tal cual
            return valor.strftime("%d/%m/%Y %H:%M")
        # Fechas de tramos cargadas como día: solo la fecha (formato.fecha_tramo).
        return formato.fecha_tramo(valor)
    if isinstance(valor, date):  # fechas sin hora
        return valor.strftime("%d/%m/%Y")
    if isinstance(valor, bool):  # verdadero/falso como Sí o No
        return "Sí" if valor else "No"
    if isinstance(valor, Decimal):  # números que vienen de PostgreSQL
        # Cantidades (sin decimales en la base) se muestran enteras; los
        # importes (NUMERIC con escala 2) conservan los dos decimales.
        # Formato argentino: 1.500,00.
        if valor.as_tuple().exponent >= 0:  # sin decimales: es una cantidad
            return formato.entero(valor)
        return formato.numero(valor, 2)
    if isinstance(valor, float):  # horas, porcentajes y promedios calculados en Python
        # Horas, porcentajes y promedios: un decimal si alcanza.
        return formato.numero(valor, 1 if round(valor, 1) == round(valor, 2) else 2)
    if isinstance(valor, (list, tuple)):  # listas (por ejemplo, medios de transporte) separadas por coma
        return ", ".join(texto(v) for v in valor)
    return str(valor)


def imprimir_tabla(tabla, vacio=None):  # muestra la tabla en la consola; la usa mostrar_y_ofrecer_csv en todos los reportes internos
    """Muestra la tabla en la consola."""
    print(f"\n=== {tabla.titulo} ===")
    if not tabla.filas:  # sin filas, solo el mensaje de vacío
        print(vacio or mensaje_vacio(tabla))
    else:
        celdas = [[texto(v) for v in fila] for fila in tabla.filas]  # pasa todos los valores a texto
        anchos = [  # ancho de cada columna: el valor más largo, hasta 40 caracteres
            min(40, max(len(str(c)), *(len(f[i]) for f in celdas)))
            for i, c in enumerate(tabla.columnas)
        ]
        print(" | ".join(str(c)[:a].ljust(a) for c, a in zip(tabla.columnas, anchos)))  # fila de títulos, alineada
        print("-+-".join("-" * a for a in anchos))
        for fila in celdas:  # cada fila, recortada y alineada al ancho de su columna
            print(" | ".join(v[:a].ljust(a) for v, a in zip(fila, anchos)))
        print(f"Total: {len(tabla.filas)} {'fila' if len(tabla.filas) == 1 else 'filas'}")
    for nota in tabla.notas:  # las aclaraciones van al final
        print(f"Nota: {nota}")


def hash_archivo(ruta):  # calcula el SHA-256 del archivo; lo usa exportar para guardarlo en la tabla reporte
    sha = hashlib.sha256()
    with open(ruta, "rb") as archivo:
        for bloque in iter(lambda: archivo.read(65536), b""):  # lee de a 64 KB para no cargar todo en memoria
            sha.update(bloque)
    return sha.hexdigest()


def escribir_csv(tabla, ruta, encabezado=()):  # escribe la tabla en CSV; la usan exportar y la opción de exportar de los reportes internos
    """CSV con separador ';' y BOM UTF-8 (se abre bien en Excel en español)."""
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)  # crea la carpeta si no existe
    with open(ruta, "w", newline="", encoding="utf-8-sig") as archivo:  # utf-8 con BOM para que Excel muestre bien los acentos
        escritor = csv.writer(archivo, delimiter=";")  # punto y coma, el separador que usa Excel en español
        for linea in encabezado:
            escritor.writerow([f"# {linea}"])
        escritor.writerow(tabla.columnas)  # fila de títulos
        for fila in tabla.filas:  # los datos, ya convertidos a texto
            escritor.writerow([texto(v) for v in fila])
    return ruta


def _latin1(valor):  # deja el texto en Latin-1 para las fuentes del PDF; la usa escribir_pdf
    """Las fuentes estándar del PDF usan Latin-1: acentos y ñ sí; flechas no."""
    return (str(valor).replace("→", "->").replace("—", "-").replace("–", "-")
            .encode("latin-1", "replace").decode("latin-1"))


def escribir_pdf(tabla, ruta, encabezado=()):  # escribe la tabla en PDF; la usa exportar para los reportes cobrables
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    pdf = FPDF(orientation="L", unit="mm", format="A4")  # A4 apaisada, para que entren las columnas
    pdf.set_auto_page_break(auto=True, margin=12)  # salta de página solo cerca del margen
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 8, _latin1(tabla.titulo), new_x="LMARGIN", new_y="NEXT")  # título en negrita
    pdf.set_font("Helvetica", "", 9)
    for linea in encabezado:  # datos del pedido: cliente, período, fecha
        pdf.cell(0, 5, _latin1(linea), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    ancho_total = pdf.w - pdf.l_margin - pdf.r_margin  # ancho útil de la hoja
    celdas = [[texto(v) for v in fila] for fila in tabla.filas]
    pesos = [  # cada columna pesa según su texto más largo (entre 4 y 30)
        max(4, min(30, max([len(str(c))] + [len(f[i]) for f in celdas])))
        for i, c in enumerate(tabla.columnas)
    ]
    anchos = [ancho_total * p / sum(pesos) for p in pesos]  # reparte el ancho de la hoja según esos pesos

    def fila_pdf(valores, negrita=False):  # dibuja una fila de celdas; se usa para los títulos y para cada fila
        pdf.set_font("Helvetica", "B" if negrita else "", 7.5)
        for valor, ancho in zip(valores, anchos):
            contenido = _latin1(valor)
            while contenido and pdf.get_string_width(contenido) > ancho - 1.5:  # recorta el texto que no entra en la celda
                contenido = contenido[:-1]
            pdf.cell(ancho, 5, contenido, border=1)
        pdf.ln(5)

    fila_pdf(tabla.columnas, negrita=True)  # títulos de las columnas
    for fila in celdas:
        if pdf.get_y() > pdf.h - 18:  # si se llega al final de la hoja, página nueva con los títulos
            pdf.add_page()
            fila_pdf(tabla.columnas, negrita=True)
        fila_pdf(fila)
    if not celdas:  # sin filas, el mensaje de vacío
        pdf.cell(0, 6, _latin1(mensaje_vacio(tabla)), new_x="LMARGIN", new_y="NEXT")
    for nota in tabla.notas:  # notas en cursiva al pie
        pdf.set_font("Helvetica", "I", 8)
        pdf.multi_cell(0, 4, _latin1(f"Nota: {nota}"), new_x="LMARGIN", new_y="NEXT")
    pdf.output(str(ruta))
    return ruta


def exportar(tabla, formato, ruta_sin_extension, encabezado=()):  # guarda el reporte cobrable en CSV o PDF; la usa reportes_cobrables_service al generar
    """Escribe CSV o PDF y devuelve (ruta, hash)."""
    formato = str(formato).upper()
    if formato == "CSV":  # elige el escritor según el formato pedido
        ruta = escribir_csv(tabla, f"{ruta_sin_extension}.csv", encabezado)
    elif formato == "PDF":
        ruta = escribir_pdf(tabla, f"{ruta_sin_extension}.pdf", encabezado)
    else:  # cualquier otro formato no se acepta
        raise ValueError("Formato inválido (CSV o PDF).")
    return ruta, hash_archivo(ruta)  # devuelve la ruta y el hash, que quedan en la tabla reporte
