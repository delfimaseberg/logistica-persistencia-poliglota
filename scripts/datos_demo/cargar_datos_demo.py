"""Carga única de datos de ejemplo para TODO el sistema (las cuatro bases).

Usa las funciones de la aplicación (repositorios y servicios), así que se
aplican las mismas reglas que en el uso normal: una factura por envío,
Entregado solo por evento, facturas de operador después de la entrega, etc.

Uso (PowerShell, desde la raíz del proyecto):

    # carga completa sobre la base de .env (PostgreSQL + MongoDB + Cassandra + Neo4j)
    python scripts\\datos_demo\\cargar_datos_demo.py --base logistica_poliglota

    # solo PostgreSQL, sobre una base descartable
    $env:POSTGRES_DB = "logistica_poliglota_demo_ensayo"
    python scripts\\datos_demo\\cargar_datos_demo.py --base logistica_poliglota_demo_ensayo --solo-postgres

    # datos adicionales (cada opción es una carga única, después de la completa)
    python scripts\\datos_demo\\cargar_datos_demo.py --base logistica_poliglota --dia3
    python scripts\\datos_demo\\cargar_datos_demo.py --base logistica_poliglota --dia3b

    # el día de la demo: lecturas IoT recientes, alertas y predicciones
    python scripts\\datos_demo\\cargar_datos_demo.py --base logistica_poliglota --refrescar-lecturas

La contraseña de los usuarios de ejemplo se toma de la variable de entorno
DEMO_PASSWORD o se pide por teclado; nunca se guarda en el repositorio.
La carga es única: si los datos de ejemplo ya existen, el script se detiene.
"""

import argparse
import math
import os
import random
import sys
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from getpass import getpass
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.database.postgres_connection import get_postgres_connection  # noqa: E402
from app.models.cliente import Cliente  # noqa: E402
from app.models.contenedor import Contenedor  # noqa: E402
from app.models.envio import Envio  # noqa: E402
from app.models.sensor import Sensor  # noqa: E402
from app.models.tramo import Tramo  # noqa: E402
from app.models.usuario import Usuario  # noqa: E402
from app.models.vehiculo import Vehiculo  # noqa: E402
from app.repositories import (  # noqa: E402
    cliente_repository, contenedor_repository, cuenta_tercero_repository,
    envio_contenedor_repository, envio_repository, facturacion_repository,
    incidente_repository, precios_repository, sensor_repository,
    terceros_repository, tramo_repository, trazabilidad_repository,
    usuario_repository, vehiculo_repository,
)
from app.services import cierre_cuenta_service, facturacion_automatica_service  # noqa: E402
from app.utils.seguridad import generar_hash_contrasena  # noqa: E402
from app.utils.validaciones_trazabilidad import (  # noqa: E402
    estado_nuevo_por_evento, validar_evento_permitido,
)

AR = ZoneInfo("America/Argentina/Buenos_Aires")
ADMIN = 4                     # usuario interno que aprueba precios y aperturas
ROL_USUARIO = 2               # rol "Usuario" existente (nivel 2)
INICIO_MINIMO = datetime(2026, 10, 30, 12, 0, tzinfo=AR)
random.seed(20261030)         # lecturas reproducibles


def t(texto):
    """'2026-10-05 08:00' en hora argentina."""
    return datetime.strptime(texto, "%Y-%m-%d %H:%M").replace(tzinfo=AR)


# ----------------------------------------------------------------- datos

CLIENTES = {
    # clave: (razón social, identificación fiscal, email, teléfono, dirección, país)
    "VINEDOS": ("Viñedos del Pacífico SpA", "76.543.210-K", "compras@vinedos.example",
                "+56 2 2345 6789", "Av. Apoquindo 4500, Santiago", "Chile"),
    "FRIGORIFICO": ("Frigorífico Oriental S.A.", "217654320019", "logistica@frigorifico.example",
                    "+598 2 901 2345", "Rambla 25 de Agosto 300, Montevideo", "Uruguay"),
    "YERBATERA": ("Yerbatera Guaraní S.A.", "80034567-1", "despachos@yerbatera.example",
                  "+595 21 445 566", "Av. Mariscal López 1200, Asunción", "Paraguay"),
}
# Clientes argentinos de los datos iniciales. En la base original ya existían
# (ids 3 y 4); en una base nueva se crean. Se buscan por CUIT.
CLIENTES_ARGENTINOS = {
    "DISTRIBUIDORA": ("Distribuidora del Sur S.A.", "30-71234567-1",
                      "administracion@distribuidoradelsur.com.ar", "11-4567-8901",
                      "Av. Rivadavia 4500, CABA", "Argentina"),
    "ALIMENTOS": ("Alimentos del Norte S.R.L.", "30-70987654-2",
                  "contacto@alimentosdelnorte.com.ar", "11-4789-2356",
                  "Av. Cabildo 3200, CABA", "Argentina"),
}

OPERADORES = {
    "ANDINOS": ("Transportes Andinos S.A.", "30-71500101-9", "operaciones@andinos.example",
                "Argentina", ["Terrestre"]),
    "NAVIERA": ("Naviera del Plata S.A.", "30-71500202-3", "trafico@navieradelplata.example",
                "Argentina", ["Marítimo"]),
    "AEROCARGA": ("AeroCarga Sur S.A.", "30-71500303-8", "cargo@aerocargasur.example",
                  "Argentina", ["Aéreo", "Terrestre"]),
}
PROVEEDORES = {
    "CONTENEDORES": ("Contenedores Patagonia S.R.L.", "30-71500404-2",
                     "ventas@contpatagonia.example", "Argentina", "CONTENEDORES"),
    "SEGUROS": ("Seguros Rumbo S.A.", "30-71500505-7", "polizas@segurosrumbo.example",
                "Argentina", "SEGUROS"),
    "SENSORES": ("TecnoSens S.A.", "30-71500606-1", "ventas@tecnosens.example",
                 "Argentina", "SENSORES"),
}
USUARIOS = [
    # (nombre, apellido, email, parte, clave de la parte)
    ("Lucía", "Rojas", "lucia.rojas@vinedos.example", "CLIENTE", "VINEDOS"),
    ("Diego", "Ferreyra", "diego.ferreyra@andinos.example", "OPERADOR", "ANDINOS"),
    ("Paula", "Méndez", "paula.mendez@navieradelplata.example", "OPERADOR", "NAVIERA"),
    ("Sofía", "Lagos", "sofia.lagos@segurosrumbo.example", "PROVEEDOR", "SEGUROS"),
]
VEHICULOS = {
    "CAMION1": ("Terrestre", "AB123CD", "ANDINOS"),
    "CAMION2": ("Terrestre", "AC456EF", "ANDINOS"),
    "BUQUE": ("Marítimo", "IMO 9123456", "NAVIERA"),
    "AVION": ("Aéreo", "LV-KCA", "AEROCARGA"),
    "CAMION3": ("Terrestre", "AD789GH", "AEROCARGA"),
}
PRECIOS = {"base": "15000", "Terrestre": "120000", "Marítimo": "450000", "Aéreo": "900000"}
COSTO_OPERADOR = {"Terrestre": Decimal("70000"), "Marítimo": Decimal("280000"),
                  "Aéreo": Decimal("600000")}

COORDS = {
    "Mendoza": (-32.8895, -68.8458), "Paso Cristo Redentor": (-32.8236, -70.0753),
    "Santiago": (-33.4489, -70.6693), "Montevideo": (-34.9011, -56.1645),
    "Buenos Aires": (-34.6037, -58.3816), "Rosario": (-32.9442, -60.6505),
    "Valencia": (39.4699, -0.3763), "Madrid": (40.4168, -3.7038),
    "Asunción": (-25.2637, -57.5759), "Clorinda": (-25.2846, -57.7185),
    "Ushuaia": (-54.8019, -68.3030), "Panamá": (8.9824, -79.5199),
    "Miami": (25.7617, -80.1918), "Córdoba": (-31.4201, -64.1888),
    "Bariloche": (-41.1335, -71.3103),
}

# Contenedores: código ISO 6346 válido, tipo, capacidad y sensores.
CONTENEDORES = {
    "C1": ("TDSU1000016", "Seco", "33.20", ["Humedad", "GPS"]),
    "C2": ("TDSU1000021", "Seco", "33.20", ["Humedad", "GPS"]),
    "C3": ("TDSU1000037", "Refrigerado", "28.30", ["Temperatura", "Humedad", "GPS"]),
    "C4": ("TDSU1000042", "Refrigerado", "28.30", ["Temperatura", "Humedad", "GPS"]),
    "C5": ("TDSU1000058", "Refrigerado", "28.30", ["Temperatura", "Humedad", "GPS"]),
    "C6": ("TDSU1000063", "Seco", "67.70", ["Humedad", "GPS", "Vibración"]),
    "C7": ("TDSU1000079", "Seco", "33.20", ["Humedad", "GPS"]),
    "C8": ("TDSU1000084", "Seco", "33.20", ["Humedad", "GPS", "Vibración"]),
    "C9": ("TDSU1000090", "Refrigerado", "28.30", ["Temperatura", "Humedad", "GPS"]),
    "C10": ("TDSU1000103", "Seco", "33.20", ["Humedad", "GPS", "Vibración"]),
    "C11": ("TDSU1000119", "Refrigerado", "28.30", ["Temperatura", "Humedad", "GPS", "Vibración"]),
    "C12": ("TDSU1000124", "Seco", "33.20", ["Humedad", "GPS"]),
}

# Envíos. Tramos: (medio, origen, destino, salida, llegada estimada, vehículo, operador).
# Eventos: (tipo, fecha, ubicación, descripción, detalle).
ENVIOS = {
    "E1": dict(cliente="VINEDOS", origen="Mendoza", destino="Santiago", prioridad="Media",
               creado="2026-08-03 09:00", contenedor="C1",
               tramos=[("Terrestre", "Mendoza", "Santiago", "2026-08-05 08:00",
                        "2026-08-07 18:00", "CAMION1", "ANDINOS")],
               eventos=[("CARGA_INICIADA", "2026-08-04 10:00", "Mendoza", "Carga de vino embotellado", {}),
                        ("EN_TRANSITO", "2026-08-05 08:00", "Mendoza", "Salida hacia Chile", {}),
                        ("ADUANA", "2026-08-06 12:00", "Paso Cristo Redentor", "Control aduanero",
                         {"documento": "DUA-CL-1001"}),
                        ("DESCARGA", "2026-08-07 15:00", "Santiago", "Descarga en depósito", {}),
                        ("ENTREGADO", "2026-08-07 17:00", "Santiago", "Entregado al cliente", {})]),
    "E2": dict(cliente="VINEDOS", origen="Mendoza", destino="Santiago", prioridad="Media",
               creado="2026-09-01 09:00", contenedor="C2",
               tramos=[("Terrestre", "Mendoza", "Santiago", "2026-09-02 08:00",
                        "2026-09-04 18:00", "CAMION1", "ANDINOS")],
               eventos=[("CARGA_INICIADA", "2026-09-01 15:00", "Mendoza", "Carga de vino", {}),
                        ("EN_TRANSITO", "2026-09-02 08:00", "Mendoza", "Salida hacia Chile", {}),
                        ("RETRASO", "2026-09-03 10:00", "Paso Cristo Redentor",
                         "Paso cerrado por nevadas", {"motivo": "Paso Cristo Redentor cerrado por nevadas",
                                                       "demora_horas": 72}),
                        ("ADUANA", "2026-09-06 11:00", "Paso Cristo Redentor", "Control aduanero",
                         {"documento": "DUA-CL-1002"}),
                        ("DESCARGA", "2026-09-07 14:00", "Santiago", "Descarga en depósito", {}),
                        ("ENTREGADO", "2026-09-07 16:00", "Santiago", "Entregado con demora", {})],
               incidentes=[("Retraso", "Alta", "Paso Cristo Redentor cerrado por nevadas (72 h)",
                            "2026-09-03 10:00", "Cerrado")]),
    "E3": dict(cliente="VINEDOS", origen="Mendoza", destino="Santiago", prioridad="Alta",
               creado="2026-10-01 09:00", contenedor="C3",
               tramos=[("Terrestre", "Mendoza", "Santiago", "2026-10-02 08:00",
                        "2026-10-04 18:00", "CAMION2", "ANDINOS")],
               eventos=[("CARGA_INICIADA", "2026-10-01 16:00", "Mendoza", "Carga refrigerada", {}),
                        ("EN_TRANSITO", "2026-10-02 08:00", "Mendoza", "Salida hacia Chile", {}),
                        ("RETRASO", "2026-10-03 09:00", "Paso Cristo Redentor",
                         "Demoras en control aduanero", {"motivo": "Demoras en control aduanero",
                                                         "demora_horas": 48}),
                        ("ADUANA", "2026-10-05 10:00", "Paso Cristo Redentor", "Control aduanero",
                         {"documento": "DUA-CL-1003"}),
                        ("ENTREGADO", "2026-10-06 18:00", "Santiago", "Entregado con demora", {})],
               incidentes=[("Retraso", "Media", "Demoras en control aduanero (48 h)",
                            "2026-10-03 09:00", "Cerrado")]),
    "E4": dict(cliente="FRIGORIFICO", origen="Montevideo", destino="Rosario", prioridad="Alta",
               creado="2026-09-10 09:00", contenedor="C4",
               tramos=[("Marítimo", "Montevideo", "Buenos Aires", "2026-09-11 20:00",
                        "2026-09-12 10:00", "BUQUE", "NAVIERA"),
                       ("Terrestre", "Buenos Aires", "Rosario", "2026-09-12 14:00",
                        "2026-09-12 22:00", "CAMION2", "ANDINOS")],
               eventos=[("CARGA_INICIADA", "2026-09-11 10:00", "Montevideo", "Carga de carne congelada", {}),
                        ("EN_TRANSITO", "2026-09-11 20:00", "Montevideo", "Zarpada", {}),
                        ("ADUANA", "2026-09-12 09:00", "Buenos Aires", "Puerto de Buenos Aires",
                         {"documento": "DUA-AR-2004"}),
                        ("DESCARGA", "2026-09-12 21:00", "Rosario", "Descarga en cámara", {}),
                        ("ENTREGADO", "2026-09-12 21:30", "Rosario", "Entregado", {})],
               incidentes=[("Temperatura alta", "Alta", "Corte de energía del reefer durante 2 h",
                            "2026-09-12 03:00", "Cerrado")]),
    "E5": dict(cliente="FRIGORIFICO", origen="Montevideo", destino="Rosario", prioridad="Alta",
               creado="2026-10-05 09:00", contenedor="C5",
               tramos=[("Marítimo", "Montevideo", "Buenos Aires", "2026-10-06 20:00",
                        "2026-10-07 10:00", "BUQUE", "NAVIERA"),
                       ("Terrestre", "Buenos Aires", "Rosario", "2026-10-07 14:00",
                        "2026-10-07 22:00", "CAMION2", "ANDINOS")],
               eventos=[("CARGA_INICIADA", "2026-10-06 10:00", "Montevideo", "Carga de carne", {}),
                        ("EN_TRANSITO", "2026-10-06 20:00", "Montevideo", "Zarpada", {}),
                        ("ADUANA", "2026-10-07 09:00", "Buenos Aires", "Puerto de Buenos Aires",
                         {"documento": "DUA-AR-2005"}),
                        ("ENTREGADO", "2026-10-07 21:00", "Rosario", "Entregado", {})]),
    "E6": dict(cliente="ALIMENTOS", origen="Buenos Aires", destino="Madrid", prioridad="Media",
               creado="2026-08-20 09:00", contenedor="C6",
               tramos=[("Marítimo", "Buenos Aires", "Valencia", "2026-08-22 18:00",
                        "2026-09-15 08:00", "BUQUE", "NAVIERA"),
                       ("Terrestre", "Valencia", "Madrid", "2026-09-16 08:00",
                        "2026-09-17 18:00", "CAMION3", "AEROCARGA")],
               eventos=[("CARGA_INICIADA", "2026-08-21 10:00", "Buenos Aires", "Carga de alimentos secos", {}),
                        ("EN_TRANSITO", "2026-08-22 18:00", "Buenos Aires", "Zarpada", {}),
                        ("ADUANA", "2026-09-15 10:00", "Valencia", "Aduana de Valencia",
                         {"documento": "DUA-ES-3006"}),
                        ("ENTREGADO", "2026-09-17 15:00", "Madrid", "Entregado", {})]),
    "E7": dict(cliente="YERBATERA", origen="Asunción", destino="Buenos Aires", prioridad="Baja",
               creado="2026-10-10 09:00", contenedor="C7",
               tramos=[("Terrestre", "Asunción", "Buenos Aires", "2026-10-11 07:00",
                        "2026-10-13 18:00", "CAMION3", "AEROCARGA")],
               eventos=[("CARGA_INICIADA", "2026-10-10 15:00", "Asunción", "Carga de yerba mate", {}),
                        ("EN_TRANSITO", "2026-10-11 07:00", "Asunción", "Salida", {}),
                        ("ADUANA", "2026-10-11 12:00", "Clorinda", "Frontera Clorinda",
                         {"documento": "DUA-AR-2007"}),
                        ("ENTREGADO", "2026-10-13 12:00", "Buenos Aires", "Entregado", {})]),
    "E8": dict(cliente="DISTRIBUIDORA", origen="Buenos Aires", destino="Ushuaia", prioridad="Alta",
               creado="2026-10-20 09:00", contenedor="C8",
               tramos=[("Aéreo", "Buenos Aires", "Ushuaia", "2026-10-21 07:00",
                        "2026-10-21 11:00", "AVION", "AEROCARGA")],
               eventos=[("CARGA_INICIADA", "2026-10-20 18:00", "Buenos Aires", "Carga aérea", {}),
                        ("EN_TRANSITO", "2026-10-21 07:00", "Buenos Aires", "Despegue", {}),
                        ("ENTREGADO", "2026-10-21 13:00", "Ushuaia", "Entregado", {})]),
    # En tránsito y DEMORADO (llegada estimada vencida), con incidente abierto.
    "E9": dict(cliente="VINEDOS", origen="Mendoza", destino="Santiago", prioridad="Alta",
               creado="2026-10-25 09:00", contenedor="C9",
               tramos=[("Terrestre", "Mendoza", "Santiago", "2026-10-26 08:00",
                        "2026-10-28 18:00", "CAMION1", "ANDINOS")],
               eventos=[("CARGA_INICIADA", "2026-10-25 15:00", "Mendoza", "Carga refrigerada", {}),
                        ("EN_TRANSITO", "2026-10-26 08:00", "Mendoza", "Salida hacia Chile", {}),
                        ("RETRASO", "2026-10-27 09:00", "Paso Cristo Redentor",
                         "Paso cerrado por tormenta de nieve",
                         {"motivo": "Paso cerrado por tormenta de nieve", "demora_horas": 72})],
               incidentes=[("Retraso", "Alta", "Paso cerrado por tormenta de nieve (72 h)",
                            "2026-10-27 09:00", "Abierto")],
               en_transito_en="Paso Cristo Redentor"),
    # En tránsito, a tiempo (con escala).
    "E10": dict(cliente="ALIMENTOS", origen="Buenos Aires", destino="Miami", prioridad="Alta",
                creado="2026-10-28 09:00", contenedor="C10",
                tramos=[("Aéreo", "Buenos Aires", "Panamá", "2026-10-29 22:00",
                         "2026-10-30 06:00", "AVION", "AEROCARGA"),
                        ("Aéreo", "Panamá", "Miami", "2026-11-02 08:00",
                         "2026-11-02 13:00", "AVION", "AEROCARGA")],
                eventos=[("CARGA_INICIADA", "2026-10-29 12:00", "Buenos Aires", "Carga aérea", {}),
                         ("EN_TRANSITO", "2026-10-29 22:00", "Buenos Aires", "Despegue", {})],
                en_transito_en="Panamá"),
    "E11": dict(cliente="FRIGORIFICO", origen="Montevideo", destino="Rosario", prioridad="Media",
                creado="2026-10-28 10:00", contenedor="C11",
                tramos=[("Marítimo", "Montevideo", "Rosario", "2026-10-29 20:00",
                         "2026-11-01 10:00", "BUQUE", "NAVIERA")],
                eventos=[("CARGA_INICIADA", "2026-10-29 10:00", "Montevideo", "Carga de carne", {}),
                         ("EN_TRANSITO", "2026-10-29 20:00", "Montevideo", "Zarpada", {})],
                en_transito_en="Buenos Aires"),
    "E12": dict(cliente="YERBATERA", origen="Asunción", destino="Córdoba", prioridad="Media",
                creado="2026-10-29 09:00", contenedor="C12",
                tramos=[("Terrestre", "Asunción", "Córdoba", "2026-11-04 07:00",
                         "2026-11-06 18:00", "CAMION3", "AEROCARGA")],
                eventos=[]),
    "E13": dict(cliente="DISTRIBUIDORA", origen="Buenos Aires", destino="Bariloche",
                prioridad="Baja", creado="2026-10-15 09:00", contenedor=None,
                tramos=[], eventos=[], cancelar=True),
}

# Pagos de clientes: porcentaje del total (1 = total).
PAGOS_CLIENTES = {"E1": Decimal("1"), "E2": Decimal("1"), "E3": Decimal("0.4"),
                  "E4": Decimal("0.5"), "E6": Decimal("1"), "E8": Decimal("1")}

# Facturas de operadores por tramo: (envío, índice de tramo, comprobante, emisión, pago).
FACTURAS_OPERADORES = [
    ("E1", 0, "A-0001-00000101", "2026-08-10", "TOTAL"),
    ("E2", 0, "A-0001-00000117", "2026-09-10", "TOTAL"),
    ("E3", 0, "A-0001-00000134", "2026-10-08", None),
    ("E4", 0, "A-0007-00002210", "2026-09-13", None),          # vencida
    ("E4", 1, "A-0001-00000122", "2026-09-14", "TOTAL"),
    ("E5", 0, "A-0007-00002298", "2026-10-09", None),
    ("E5", 1, "A-0001-00000136", "2026-10-09", "PARCIAL"),
    ("E6", 0, "A-0007-00002150", "2026-09-18", "TOTAL"),
    ("E6", 1, "B-0003-00000410", "2026-09-19", "TOTAL"),
    ("E7", 0, "B-0003-00000455", "2026-10-14", None),
    ("E8", 0, "B-0003-00000470", "2026-10-22", "PARCIAL"),
]
# Facturas de proveedores: (proveedor, comprobante, concepto, emisión, vencimiento, total, pago).
FACTURAS_PROVEEDORES = [
    ("CONTENEDORES", "A-0002-00001001", "Alquiler de 12 contenedores - septiembre 2026",
     "2026-09-30", None, Decimal("360000"), "TOTAL"),
    ("CONTENEDORES", "A-0002-00001045", "Alquiler de 12 contenedores - octubre 2026",
     "2026-10-30", None, Decimal("360000"), None),
    ("SEGUROS", "A-0010-00000777", "Póliza de carga internacional - envío Buenos Aires/Madrid",
     "2026-08-21", None, Decimal("95000"), "PARCIAL"),
    ("SENSORES", "A-0004-00000210", "Compra de 32 sensores IoT y gateways",
     "2026-10-05", "2026-10-20", Decimal("640000"), None),
]

MENSAJES = [
    # (remitente, destinatario, contenido); "ADMIN" = usuario interno 4
    ("ANDINOS", "ADMIN", "El envío Mendoza-Santiago está detenido en el Paso Cristo Redentor "
                         "por tormenta de nieve. Estimamos 72 h de demora."),
    ("ADMIN", "ANDINOS", "Gracias, Diego. Le aviso al cliente y seguimos el contenedor por GPS."),
    ("ADMIN", "VINEDOS", "Lucía: su envío a Santiago está demorado por cierre del paso. "
                         "Le informamos la nueva fecha apenas reabra."),
    ("VINEDOS", "ADMIN", "Gracias. ¿Qué temperatura está registrando el contenedor refrigerado?"),
    ("SEGUROS", "ADMIN", "Les recordamos el saldo pendiente de la póliza de carga del envío a Madrid."),
    ("NAVIERA", "ADMIN", "La factura del tramo marítimo Montevideo-Buenos Aires de septiembre está vencida. "
                         "¿Nos confirman fecha de pago?"),
]


# --------------------------------------------------------------- utilidades

class Carga:
    def __init__(self, solo_postgres):
        self.solo_postgres = solo_postgres
        self.ids = {"cliente": {}, "operador": {}, "proveedor": {},
                    "vehiculo": {}, "contenedor": {}, "sensor": {}, "envio": {},
                    "tramo": {}, "usuario": {"ADMIN": ADMIN}, "factura": {}}
        self.resumen = []

    def nota(self, texto):
        print(texto)
        self.resumen.append(texto)


def q(sql, params=()):
    with get_postgres_connection() as c, c.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall() if cur.description else None


def interpolar(a, b, f):
    (la1, lo1), (la2, lo2) = COORDS[a], COORDS[b]
    return round(la1 + (la2 - la1) * f, 6), round(lo1 + (lo2 - lo1) * f, 6)


def pedir_contrasena():
    clave = os.getenv("DEMO_PASSWORD")
    if clave:
        return clave
    clave = getpass("Contraseña para los usuarios de ejemplo: ")
    if not clave or clave != getpass("Repetir contraseña: "):
        sys.exit("Las contraseñas no coinciden o están vacías.")
    return clave


# ----------------------------------------------------------------- fases PG

def cargar_maestros(c, clave):
    c.argentinos_nuevos = []
    for k, (rs, cuit, email, tel, dirc, pais) in CLIENTES_ARGENTINOS.items():
        existente = q("SELECT id_cliente FROM cliente WHERE cuit = %s", (cuit,))
        if existente:
            c.ids["cliente"][k] = existente[0][0]
        else:
            c.ids["cliente"][k] = cliente_repository.crear_cliente(
                Cliente(rs, cuit, email, tel, dirc, pais, "ACTIVO"))
            c.argentinos_nuevos.append(k)
    for k, (rs, cuit, email, tel, dirc, pais) in CLIENTES.items():
        c.ids["cliente"][k] = cliente_repository.crear_cliente(
            Cliente(rs, cuit, email, tel, dirc, pais, "ACTIVO"))
    for k, (rs, cuit, email, pais, modalidades) in OPERADORES.items():
        c.ids["operador"][k] = terceros_repository.crear_operador({
            "razon_social": rs, "cuit": cuit, "email": email, "telefono": None,
            "direccion": None, "pais": pais, "modalidades": modalidades})
    for k, (rs, cuit, email, pais, rubro) in PROVEEDORES.items():
        c.ids["proveedor"][k] = terceros_repository.crear_proveedor({
            "razon_social": rs, "cuit": cuit, "email": email, "telefono": None,
            "direccion": None, "pais": pais, "rubro": rubro})
    for nombre, apellido, email, parte, k in USUARIOS:
        # Un hash (con su propia sal) por usuario.
        hash_clave = generar_hash_contrasena(clave)
        partes = {"id_cliente": None, "id_proveedor": None, "id_operador": None}
        if parte == "CLIENTE":
            partes["id_cliente"] = c.ids["cliente"][k]
        elif parte == "OPERADOR":
            partes["id_operador"] = c.ids["operador"][k]
        else:
            partes["id_proveedor"] = c.ids["proveedor"][k]
        c.ids["usuario"][k] = usuario_repository.crear_usuario(Usuario(
            partes["id_cliente"], ROL_USUARIO, nombre, apellido, email, hash_clave, "ACTIVO",
            id_proveedor=partes["id_proveedor"], id_operador=partes["id_operador"]))
    for k, (tipo, ident, op) in VEHICULOS.items():
        c.ids["vehiculo"][k] = vehiculo_repository.crear_vehiculo(
            Vehiculo(tipo, ident, None, "Disponible", c.ids["operador"][op]))
    for k, (codigo, tipo, capacidad, sensores) in CONTENEDORES.items():
        id_cont = contenedor_repository.crear_contenedor(
            Contenedor(codigo, tipo, Decimal(capacidad), "Disponible"))
        c.ids["contenedor"][k] = id_cont
        c.ids["sensor"][k] = {
            tipo_s: sensor_repository.crear_sensor(Sensor(
                id_cont, tipo_s, "TecnoSens", date(2026, 7, 15), "Activo"))
            for tipo_s in sensores}
    c.nota(f"Maestros: {len(CLIENTES)} clientes nuevos, {len(OPERADORES)} operadores, "
           f"{len(PROVEEDORES)} proveedores, {len(USUARIOS)} usuarios, {len(VEHICULOS)} vehículos, "
           f"{len(CONTENEDORES)} contenedores con "
           f"{sum(len(x[3]) for x in CONTENEDORES.values())} sensores.")


def cargar_precios(c):
    precios_repository.definir_tarifa_estandar(
        PRECIOS["base"], {m: PRECIOS[m] for m in ("Terrestre", "Marítimo", "Aéreo")},
        ADMIN, "Lista de precios de ejemplo 10/2026")
    c.nota("Precios: TARIFA_ESTANDAR base 15.000; tramo terrestre 120.000, marítimo "
           "450.000, aéreo 900.000 (ARS, sin IVA).")


def registrar_evento(c, id_envio, tipo, fecha, lugar, descripcion, detalle):
    """Mismo flujo que Trazabilidad > Registrar evento, sin preguntas."""
    estado, tipos = q("SELECT estado FROM envio WHERE id_envio = %s", (id_envio,))[0][0], []
    if not c.solo_postgres:
        from app.repositories.evento_repository import insertar_evento, tipos_registrados
        tipos = tipos_registrados(id_envio)
    validar_evento_permitido(estado, tipo, tipos)
    lat, lon = COORDS.get(lugar, (None, None))
    if not c.solo_postgres:
        insertar_evento({
            "envio_id": id_envio, "tipo": tipo, "fecha_hora": fecha,
            "ubicacion": {"nombre": lugar, "lat": lat, "lon": lon},
            "descripcion": descripcion, "usuario_id": ADMIN, "detalle": detalle,
            "fecha_registro": datetime.now(timezone.utc)})
    nuevo = estado_nuevo_por_evento(tipo, estado)
    if nuevo:
        if not trazabilidad_repository.actualizar_estado_envio(
                id_envio, nuevo, fecha if tipo == "ENTREGADO" else None):
            raise RuntimeError(f"No se pudo pasar el envío {id_envio} a {nuevo}")


def cargar_envios(c):
    for k, e in ENVIOS.items():
        # Desde la migración 014 un envío nuevo exige país de origen y destino.
        id_envio = envio_repository.crear_envio(
            Envio(c.ids["cliente"][e["cliente"]], e["origen"], e["destino"], "Pendiente",
                  e["prioridad"], pais_origen=PAIS_DE[e["origen"]],
                  pais_destino=PAIS_DE[e["destino"]]),
            fecha_creacion=t(e["creado"]))
        c.ids["envio"][k] = id_envio
        c.ids["tramo"][k] = []
        for medio, ori, dest, sal, lleg, veh, op in e["tramos"]:
            c.ids["tramo"][k].append(tramo_repository.crear_tramo(Tramo(
                id_envio, c.ids["vehiculo"][veh], medio, ori, dest, t(sal), t(lleg),
                c.ids["operador"][op])))
        if e["contenedor"]:
            if not envio_contenedor_repository.asociar_contenedor_db(
                    id_envio, c.ids["contenedor"][e["contenedor"]]):
                raise RuntimeError(f"No se pudo asociar el contenedor de {k}")
        for tipo, fecha, lugar, desc, detalle in e["eventos"]:
            registrar_evento(c, id_envio, tipo, t(fecha), lugar, desc, detalle)
        for tipo, sev, desc, fecha, estado in e.get("incidentes", []):
            id_inc = incidente_repository.crear_incidente(id_envio, tipo, sev, desc, t(fecha))
            if estado == "Cerrado":
                incidente_repository.actualizar_estado_incidente(id_inc, "Cerrado")
        if e.get("cancelar"):
            envio_repository.actualizar_envio(id_envio, Envio(
                c.ids["cliente"][e["cliente"]], e["origen"], e["destino"], "Cancelado",
                e["prioridad"]))
    estados = q("SELECT estado, count(*) FROM envio WHERE id_envio = ANY(%s) GROUP BY 1 ORDER BY 1",
                (list(c.ids["envio"].values()),))
    c.nota(f"Envíos: {len(ENVIOS)} ({', '.join(f'{n} {s}' for s, n in estados)}); "
           f"tramos: {sum(len(v) for v in c.ids['tramo'].values())}.")


def cargar_aperturas(c):
    # Los clientes argentinos que ya existían tienen su propia apertura; si la
    # carga los creó (base nueva), se abren igual que los demás.
    nuevos = list(CLIENTES) + getattr(c, "argentinos_nuevos", [])
    for k in nuevos:
        cierre_cuenta_service.registrar_apertura(
            c.ids["cliente"][k], Decimal("0"), date(2026, 10, 1),
            "Cliente nuevo: sin documentos anteriores al 01/10/2026.", ADMIN)
    c.nota(f"Aperturas: {len(nuevos)} clientes nuevos con saldo 0 al 01/10/2026 (sin "
           "documentos anteriores; sus facturas tienen movimiento).")


def cargar_facturacion(c):
    auto1 = facturacion_automatica_service.procesar_facturacion_automatica(date(2026, 9, 30))
    manuales = [facturacion_repository.emitir_factura_envio(c.ids["envio"][k], "ENVIO_MANUAL")
                for k in ("E3", "E7")]
    hoy = facturacion_automatica_service.hoy_argentina()
    auto2 = facturacion_automatica_service.procesar_facturacion_automatica(hoy)
    auto3 = facturacion_automatica_service.procesar_facturacion_automatica(hoy)
    por_envio = dict(q("SELECT id_envio, id_factura FROM factura WHERE id_envio = ANY(%s)",
                       (list(c.ids["envio"].values()),)))
    c.ids["factura"] = {k: por_envio.get(v) for k, v in c.ids["envio"].items()}
    c.nota(f"Facturación: automática al 30/09 -> {len(auto1['facturados'])} facturas; "
           f"manual -> {len(manuales)}; automática a hoy -> {len(auto2['facturados'])}; "
           f"reejecución -> {len(auto3['facturados'])} (idempotente).")

    for k, proporcion in PAGOS_CLIENTES.items():
        id_factura = c.ids["factura"][k]
        total = q("SELECT total FROM factura WHERE id_factura = %s", (id_factura,))[0][0]
        monto = (total * proporcion).quantize(Decimal("0.01"))
        facturacion_repository.registrar_pago(id_factura, monto, "Transferencia")
    c.nota(f"Pagos de clientes: {len(PAGOS_CLIENTES)} (totales y parciales); "
           "2 facturas quedan pendientes.")


def cargar_cuentas_terceros(c):
    hoy = facturacion_automatica_service.hoy_argentina()
    for k, i, numero, emision, pago in FACTURAS_OPERADORES:
        id_tramo = c.ids["tramo"][k][i]
        medio, op = q("SELECT medio_transporte, id_operador FROM tramo WHERE id_tramo = %s",
                      (id_tramo,))[0]
        total = COSTO_OPERADOR[medio]
        id_fr = cuenta_tercero_repository.registrar_factura_recibida(
            "OPERADOR", op, numero, total, date.fromisoformat(emision), id_tramo=id_tramo,
            registrado_por=ADMIN, hoy=hoy)
        if pago:
            monto = total if pago == "TOTAL" else (total / 2).quantize(Decimal("0.01"))
            cuenta_tercero_repository.registrar_pago_emitido(
                id_fr, monto, "Transferencia", f"OP-{numero}", registrado_por=ADMIN)
    for k, numero, concepto, emision, venc, total, pago in FACTURAS_PROVEEDORES:
        id_fr = cuenta_tercero_repository.registrar_factura_recibida(
            "PROVEEDOR", c.ids["proveedor"][k], numero, total, date.fromisoformat(emision),
            date.fromisoformat(venc) if venc else None, concepto=concepto,
            registrado_por=ADMIN, hoy=hoy)
        if pago:
            monto = total if pago == "TOTAL" else (total / 2).quantize(Decimal("0.01"))
            cuenta_tercero_repository.registrar_pago_emitido(
                id_fr, monto, "Transferencia", f"OP-{numero}", registrado_por=ADMIN)
    c.nota(f"Cuentas de terceros: {len(FACTURAS_OPERADORES)} facturas de operadores y "
           f"{len(FACTURAS_PROVEEDORES)} de proveedores, con pagos totales, parciales, "
           "vencidas y por vencer.")


# ---------------------------------------------------------- fases NoSQL

def cargar_lecturas_historicas(c, saltar_existentes=False):
    """Lecturas del recorrido de cada envío terminado.

    Con saltar_existentes no se reinserta una lectura que ya está: la clave
    de lecturas_por_sensor incluye un id_lectura aleatorio, así que
    reinsertar crearía otra fila en vez de sobrescribir.
    """
    from app.repositories.lectura_iot_repository import (
        existe_lectura_sensor, registrar_lectura_db)
    total = salteadas = 0
    for k, e in ENVIOS.items():
        # Solo envíos terminados (con evento ENTREGADO): los en tránsito
        # reciben lecturas recientes y los pendientes todavía no salieron.
        if not e["contenedor"] or not any(tp == "ENTREGADO" for tp, *_ in e["eventos"]):
            continue
        cont = c.ids["contenedor"][e["contenedor"]]
        sensores = c.ids["sensor"][e["contenedor"]]
        inicio = t(e["tramos"][0][3])
        fin = next(t(f) for tp, f, *_ in e["eventos"] if tp == "ENTREGADO")
        paradas = [e["tramos"][0][1]] + [tr[2] for tr in e["tramos"]]
        pasos = max(4, int((fin - inicio).total_seconds() // (6 * 3600)))
        for paso in range(pasos + 1):
            f = paso / pasos
            momento = inicio + (fin - inicio) * f
            tramo = min(int(f * (len(paradas) - 1)), len(paradas) - 2)
            local = f * (len(paradas) - 1) - tramo
            lat, lon = interpolar(paradas[tramo], paradas[tramo + 1], local)
            frio = CONTENEDORES[e["contenedor"]][1] == "Refrigerado"
            for tipo_s, id_sensor in sensores.items():
                v = {"bateria": round(95 - 30 * f, 1)}
                if tipo_s == "GPS":
                    v.update(gps_latitud=lat, gps_longitud=lon)
                elif tipo_s == "Temperatura":
                    v["temperatura"] = round(random.uniform(3, 6), 2)
                    if k == "E4" and 0.45 < f < 0.6:      # corte del reefer
                        v["temperatura"] = round(random.uniform(9, 11), 2)
                elif tipo_s == "Humedad":
                    v["humedad"] = round(random.uniform(60 if frio else 40, 75), 1)
                elif tipo_s == "Vibración":
                    v["vibracion"] = round(random.uniform(1, 9), 2)
                if saltar_existentes and existe_lectura_sensor(id_sensor, momento):
                    salteadas += 1
                    continue
                registrar_lectura_db(id_sensor, cont, fecha_hora=momento, **v)
                total += 1
    c.nota(f"Cassandra: {total} lecturas históricas nuevas (agosto a octubre, con GPS del "
           f"recorrido); {salteadas} ya existían y no se duplicaron.")


def cargar_lecturas_recientes(c):
    """Lecturas de las últimas 6 h para los envíos en tránsito, con anomalías."""
    from app.repositories.lectura_iot_repository import registrar_lectura_db
    ahora = datetime.now(timezone.utc)
    total = 0
    for k in ("E9", "E10", "E11"):
        e = ENVIOS[k]
        cont = c.ids["contenedor"][e["contenedor"]]
        lat0, lon0 = COORDS[e["en_transito_en"]]
        for h in range(6, -1, -2):
            momento = ahora - timedelta(hours=h, minutes=30 + random.randint(0, 20))
            for tipo_s, id_sensor in c.ids["sensor"][e["contenedor"]].items():
                if k == "E11" and tipo_s == "Vibración":
                    continue        # sensor activo que no transmite (alerta de estado)
                v = {"bateria": 80.0}
                if tipo_s == "GPS":
                    v.update(gps_latitud=round(lat0 + random.uniform(-0.02, 0.02), 6),
                             gps_longitud=round(lon0 + random.uniform(-0.02, 0.02), 6))
                    if k == "E10":
                        v["bateria"] = 15.0 if h == 0 else 22.0   # batería baja
                elif tipo_s == "Temperatura":
                    v["temperatura"] = 11.4 if (k == "E9" and h == 0) else round(random.uniform(3, 6), 2)
                elif tipo_s == "Humedad":
                    v["humedad"] = round(random.uniform(55, 72), 1)
                elif tipo_s == "Vibración":
                    v["vibracion"] = round(random.uniform(1, 6), 2)
                registrar_lectura_db(id_sensor, cont, fecha_hora=momento, **v)
                total += 1
    c.nota(f"Cassandra: {total} lecturas recientes (E9 temperatura alta, E10 batería baja, "
           "E11 un sensor sin transmitir).")


def detectar_alertas_y_predicciones(c, ids_contenedores):
    """Igual que 'Detectar anomalías IoT' y los procesos periódicos, sin preguntas."""
    from app.repositories.lectura_iot_repository import consultar_ultima_lectura_db
    from app.services.alertas_service import emitir_alerta as registrar_alerta
    from app.services.incidentes_service import (
        buscar_envios_activos_de_contenedor, detectar_anomalias, procesar_incidente_de_alerta)
    from app.services.procesos_periodicos_service import detectar_sensores_inactivos_automatico
    from app.services.predicciones_service import actualizar_predicciones_activas

    limite = datetime.now(timezone.utc) - timedelta(hours=24)
    alertas = incidentes = 0
    for id_cont in ids_contenedores:
        for id_sensor, *_ in q("SELECT id_sensor FROM sensor_iot WHERE id_contenedor = %s "
                               "AND estado = 'Activo'", (id_cont,)):
            lectura = consultar_ultima_lectura_db(id_sensor)
            if lectura is None:
                continue
            fecha = lectura.fecha_hora
            fecha = fecha if fecha.tzinfo else fecha.replace(tzinfo=timezone.utc)
            if fecha < limite:
                continue
            envios = buscar_envios_activos_de_contenedor(id_cont)
            id_envio = envios[0] if len(envios) == 1 else None
            for tipo, sev, desc in detectar_anomalias(lectura):
                alerta = registrar_alerta(sensor_id=id_sensor, contenedor_id=id_cont, tipo=tipo,
                                          severidad=sev, descripcion=desc,
                                          lectura_id=lectura.id_lectura, envio_id=id_envio)
                alertas += 1
                if id_envio:
                    procesar_incidente_de_alerta(alerta, id_envio, id_sensor, lectura.id_lectura,
                                                 tipo, sev, desc)
                    incidentes += 1
    inactivos = detectar_sensores_inactivos_automatico(horas=24)
    predicciones = actualizar_predicciones_activas()
    c.nota(f"MongoDB: {alertas} alertas por anomalías ({incidentes} con incidente), "
           f"{inactivos['alertas_procesadas']} alertas de sensores sin transmisión, "
           f"{predicciones['guardadas']} predicciones de riesgo.")


def cargar_mensajes(c):
    from app.repositories.mensajeria_repository import (
        agregar_miembro_grupo, crear_grupo, registrar_mensaje_grupo, registrar_mensaje_privado)
    from app.database.mongo_connection import get_mongo_database
    db = get_mongo_database()
    u = c.ids["usuario"]
    for rem, dest, texto in MENSAJES:
        if not db.mensajes.find_one({"remitente_id": u[rem], "contenido": texto}):
            registrar_mensaje_privado(u[rem], u[dest], texto)
    existente = db.grupos_trabajo.find_one({"nombre": "Operación Chile", "creador_id": ADMIN})
    if existente is None:
        grupo = crear_grupo("Operación Chile", "Seguimiento de envíos Mendoza-Santiago", ADMIN)
        for k in ("ANDINOS", "VINEDOS"):
            agregar_miembro_grupo(grupo, u[k])
        registrar_mensaje_grupo(ADMIN, grupo, "Abrimos este grupo para coordinar el envío demorado en el paso.")
        registrar_mensaje_grupo(u["ANDINOS"], grupo, "El paso reabriría mañana a las 8. Les aviso al cruzar.")
    c.nota(f"MongoDB: {len(MENSAJES)} mensajes privados y un grupo de trabajo con cliente, "
           "operador y administración.")


def sincronizar_grafo(c):
    from app.services.sincronizacion_service import resincronizar_todos
    correctos, errores = resincronizar_todos()
    c.nota(f"Neo4j: {correctos} envíos sincronizados; errores: {errores}.")


# ------------------------------------------------- datos adicionales (--dia3)
# Países de los envíos, envío demorado, partidas de carga, incidentes y
# reportes cobrables.

PAIS_DE = {
    "Mendoza": "Argentina", "Paso Cristo Redentor": "Argentina", "Santiago": "Chile",
    "Montevideo": "Uruguay", "Buenos Aires": "Argentina", "Rosario": "Argentina",
    "Valencia": "España", "Madrid": "España", "Asunción": "Paraguay",
    "Clorinda": "Argentina", "Ushuaia": "Argentina", "Panamá": "Panamá",
    "Miami": "Estados Unidos", "Córdoba": "Argentina", "Bariloche": "Argentina",
    "Uspallata": "Argentina",
}
COORDS["Uspallata"] = (-32.5931, -69.3466)
TIPOS_CARGA = {
    "VINO": "Vino embotellado", "CARNE": "Carne congelada",
    "ALIMENTOS": "Alimentos secos", "YERBA": "Yerba mate", "GENERAL": "Carga general",
}
# Partidas por envío: (tipo, peso kg, frágil).
PARTIDAS = {
    "E1": [("VINO", "18000", True)], "E2": [("VINO", "19500", True)],
    "E3": [("VINO", "17200", True)], "E4": [("CARNE", "24000", False)],
    "E5": [("CARNE", "22500", False)],
    "E6": [("ALIMENTOS", "26000", False), ("GENERAL", "3500", False)],
    "E7": [("YERBA", "21000", False)], "E8": [("GENERAL", "2800", True)],
    "E9": [("VINO", "18800", True)], "E10": [("GENERAL", "4200", True)],
    "E11": [("CARNE", "23800", False)], "E12": [("YERBA", "20500", False)],
    "E14": [("VINO", "19000", True)],
}
INCIDENTES_DIA3 = [
    ("E7", "Control fronterizo demorado", "Media", "Demora de 6 h en el paso de Clorinda",
     "2026-10-11 12:00"),
    ("E5", "Daño en embalaje", "Baja", "Pallet con film roto; sin pérdida de mercadería",
     "2026-10-07 21:30"),
]
# Envío demorado nuevo (el anterior se entregó el 30/10).
ENVIO_DEMORADO = dict(
    clave="E14", cliente="VINEDOS", origen="Mendoza", destino="Santiago", prioridad="Alta",
    creado="2026-10-27 09:00", contenedor=("C13", "TDSU1000130", "Refrigerado", "28.30",
                                           ["Temperatura", "Humedad", "GPS"]),
    tramo=("Terrestre", "Mendoza", "Santiago", "2026-10-28 08:00", "2026-10-30 12:00",
           "CAMION2", "ANDINOS"),
    eventos=[("CARGA_INICIADA", "2026-10-27 15:00", "Mendoza", "Carga refrigerada", {}),
             ("EN_TRANSITO", "2026-10-28 08:00", "Mendoza", "Salida hacia Chile", {}),
             ("RETRASO", "2026-10-29 10:00", "Uspallata", "Corte de ruta por protesta",
              {"motivo": "Corte de ruta por protesta en Uspallata", "demora_horas": 36})],
    incidente=("Retraso", "Alta", "Corte de ruta por protesta en Uspallata (36 h)",
               "2026-10-29 10:00"),
    en_transito_en="Uspallata",
)
REPORTES_DEMO = [
    # (usuario: clave de USUARIOS o "ADMIN", cliente, tipo, formato, desde)
    ("VINEDOS", "VINEDOS", "PUNTUALIDAD", "CSV", "2026-08-01"),
    ("VINEDOS", "VINEDOS", "CONDICIONES_CARGA", "PDF", "2026-10-01"),
    ("ADMIN", "FRIGORIFICO", "INCIDENTES", "CSV", "2026-09-01"),
]


def _id_envio_por_clave(e):
    fila = q("SELECT id_envio FROM envio WHERE origen = %s AND destino = %s "
             "AND fecha_creacion = %s", (e["origen"], e["destino"], t(e["creado"])))
    return fila[0][0] if fila else None


def cargar_dia3(c):
    from app.repositories import tarifas_repository
    from app.services import reportes_cobrables_service as cobrables

    # 1. Países de los envíos de ejemplo (los de prueba viejos quedan sin dato).
    for k, e in ENVIOS.items():
        envio_repository.actualizar_paises_envio(
            c.ids["envio"][k], PAIS_DE[e["origen"]], PAIS_DE[e["destino"]])
    c.nota(f"Países de origen y destino en {len(ENVIOS)} envíos de ejemplo.")

    # 2. Envío demorado nuevo, con incidente abierto.
    d = ENVIO_DEMORADO
    kc, codigo, tipo_c, capacidad, sensores = d["contenedor"]
    id_cont = contenedor_repository.crear_contenedor(
        Contenedor(codigo, tipo_c, Decimal(capacidad), "Disponible"))
    c.ids["contenedor"][kc] = id_cont
    c.ids["sensor"][kc] = {s: sensor_repository.crear_sensor(Sensor(
        id_cont, s, "TecnoSens", date(2026, 10, 20), "Activo")) for s in sensores}
    id_envio = envio_repository.crear_envio(
        Envio(c.ids["cliente"][d["cliente"]], d["origen"], d["destino"], "Pendiente",
              d["prioridad"], pais_origen=PAIS_DE[d["origen"]],
              pais_destino=PAIS_DE[d["destino"]]),
        fecha_creacion=t(d["creado"]))
    c.ids["envio"][d["clave"]] = id_envio
    medio, ori, dest, sal, lleg, veh, op = d["tramo"]
    tramo_repository.crear_tramo(Tramo(id_envio, c.ids["vehiculo"][veh], medio, ori, dest,
                                       t(sal), t(lleg), c.ids["operador"][op]))
    if not envio_contenedor_repository.asociar_contenedor_db(id_envio, id_cont):
        raise RuntimeError("No se pudo asociar el contenedor del envío demorado.")
    for tipo, fecha, lugar, desc, detalle in d["eventos"]:
        registrar_evento(c, id_envio, tipo, t(fecha), lugar, desc, detalle)
    tipo_i, sev, desc, fecha = d["incidente"]
    incidente_repository.crear_incidente(id_envio, tipo_i, sev, desc, t(fecha))
    ENVIOS[d["clave"]] = dict(contenedor=kc, en_transito_en=d["en_transito_en"])
    c.nota(f"Envío demorado {id_envio} (Mendoza -> Santiago, llegada estimada 30/10 12:00) "
           "con evento RETRASO e incidente de Retraso abierto.")

    # 3. Partidas de carga (peso real) para el ranking por volumen.
    existentes = {r[0] for r in tarifas_repository.listar_tipos_carga()}
    for codigo_t, descripcion in TIPOS_CARGA.items():
        if codigo_t not in existentes:
            tarifas_repository.crear_tipo_carga(codigo_t, descripcion)
    total_kg = Decimal("0")
    for k, partidas in PARTIDAS.items():
        for tipo_carga, peso, fragil in partidas:
            tarifas_repository.agregar_carga(c.ids["envio"][k], tipo_carga, Decimal(peso), fragil,
                                             TIPOS_CARGA[tipo_carga])
            total_kg += Decimal(peso)
    c.nota(f"Partidas de carga: {sum(len(p) for p in PARTIDAS.values())} ({total_kg:,.0f} kg).")

    # 4. Incidentes cerrados en Paraguay y Uruguay.
    for k, tipo_i, sev, desc, fecha in INCIDENTES_DIA3:
        id_inc = incidente_repository.crear_incidente(c.ids["envio"][k], tipo_i, sev, desc, t(fecha))
        incidente_repository.actualizar_estado_incidente(id_inc, "Cerrado")
    c.nota(f"Incidentes cerrados adicionales: {len(INCIDENTES_DIA3)}.")

    # 5. NoSQL del envío nuevo: lecturas recientes, grafo, alertas y predicciones.
    if not c.solo_postgres:
        from app.repositories.lectura_iot_repository import registrar_lectura_db
        lat0, lon0 = COORDS[d["en_transito_en"]]
        ahora = datetime.now(timezone.utc)
        for h in range(6, -1, -2):
            momento = ahora - timedelta(hours=h, minutes=30 + random.randint(0, 20))
            for tipo_s, id_sensor in c.ids["sensor"][kc].items():
                v = {"bateria": 85.0}
                if tipo_s == "GPS":
                    v.update(gps_latitud=round(lat0 + random.uniform(-0.01, 0.01), 6),
                             gps_longitud=round(lon0 + random.uniform(-0.01, 0.01), 6))
                elif tipo_s == "Temperatura":
                    v["temperatura"] = round(random.uniform(3, 6), 2)
                elif tipo_s == "Humedad":
                    v["humedad"] = round(random.uniform(55, 70), 1)
                registrar_lectura_db(id_sensor, id_cont, fecha_hora=momento, **v)
        from app.services.sincronizacion_service import sincronizar_envio_neo4j
        sincronizar_envio_neo4j(id_envio)
        from app.services.predicciones_service import actualizar_predicciones_activas
        actualizar_predicciones_activas()
        c.nota("Envío demorado: lecturas recientes en Cassandra, grafo en Neo4j y predicciones.")

    # 6. Reportes cobrables de ejemplo (generados y facturados).
    hoy = cobrables.hoy()
    for usuario, cliente, tipo, formato, desde in REPORTES_DEMO:
        if c.solo_postgres and tipo in ("OPERADORES", "CONDICIONES_CARGA", "INCIDENTES"):
            continue        # usan Neo4j, Cassandra o MongoDB
        r = cobrables.solicitar_reporte(c.ids["cliente"][cliente], c.ids["usuario"][usuario],
                                        tipo, formato, {"desde": desde, "hasta": hoy.isoformat()})
        c.nota(f"Reporte {r['id_reporte']} {tipo} {formato} para {cliente}: {r['estado']} "
               f"({r['filas']} filas, factura {r['id_factura']}).")


# ------------------------------------------------ datos adicionales (--dia3b)
# Alertas climáticas, fallas de sensor, alertas con mensajes, predicciones,
# reporte predictivo y cierre de una sesión.

# Alertas climáticas: (ubicación, fenómeno, severidad, desde, hasta, descripción)
# Desde y hasta en días respecto del día de la carga: así las vigentes lo
# siguen siendo aunque los datos se carguen otro día.
ALERTAS_CLIMA = [
    ("Mendoza", "Nevadas en alta montaña", "Alta", -1, 2,
     "Paso Cristo Redentor con cierres intermitentes."),
    ("Buenos Aires", "Tormenta fuerte", "Media", 0, 1,
     "Alerta amarilla por lluvias y ráfagas."),
    ("Uruguay", "Crecida del río", "Media", 0, 2,
     "Demoras en accesos portuarios."),
    ("Rosario", "Niebla", "Baja", -24, -23,
     "Alerta vencida: no debe afectar envíos en curso."),
]


def dia_relativo(dias):
    return datetime.now(AR).date() + timedelta(days=dias)
# Fallas de sensor: (código del contenedor, tipo de sensor, falla)
FALLAS_SENSOR = [
    ("TDSU1000103", "Humedad", "imposible"),       # envío Buenos Aires -> Miami
    ("TDSU1000119", "Temperatura", "congelada"),   # envío Montevideo -> Rosario
    # envío Buenos Aires -> Madrid de los datos iniciales; en una base nueva
    # (sin esos datos) se usa el contenedor del envío demorado de --dia3.
    (("MSCU1234571", "TDSU1000130"), "Temperatura", "salto"),
]
REPORTE_PREDICTIVO = ("VINEDOS", "VINEDOS", "PREDICTIVO", "CSV")
SESION_DEMO = "VINEDOS"      # usuario cuya sesión cierra el administrador


def cargar_dia3b(c):
    from app.repositories import sesion_repository
    from app.services import reportes_cobrables_service as cobrables

    if not c.solo_postgres:
        from app.repositories.alerta_climatica_repository import registrar_alerta_climatica
        from app.repositories.lectura_iot_repository import registrar_lectura_db
        from app.repositories.regla_alerta_repository import reglas_vigentes, umbral
        from app.services.procesos_periodicos_service import (
            ejecutar_predicciones_diarias, ejecutar_revision_sensores)
        from app.services.simulacion_fallas_service import lecturas_de_falla

        # 1. Alertas climáticas (fuente del riesgo climático).
        for ubicacion, fenomeno, severidad, desde, hasta, descripcion in ALERTAS_CLIMA:
            registrar_alerta_climatica(ubicacion, fenomeno, severidad, dia_relativo(desde),
                                       dia_relativo(hasta), ADMIN, descripcion)
        c.nota(f"MongoDB: {len(ALERTAS_CLIMA)} alertas climáticas (una vencida).")

        # 2. Lecturas con fallas de sensor (Cassandra).
        vigentes = reglas_vigentes()
        ahora = datetime.now(timezone.utc) - timedelta(minutes=1)
        for codigos, tipo_sensor, falla in FALLAS_SENSOR:
            codigos = (codigos,) if isinstance(codigos, str) else codigos
            for codigo in codigos:          # el primero que exista
                fila = q("""SELECT s.id_sensor, s.id_contenedor FROM sensor_iot s
                            JOIN contenedor ct ON ct.id_contenedor = s.id_contenedor
                            WHERE ct.codigo_internacional = %s AND s.tipo = %s
                              AND s.estado = 'Activo'""", (codigo, tipo_sensor))
                if len(fila) == 1:
                    break
            if len(fila) != 1:
                raise RuntimeError(f"No se identifica el sensor {tipo_sensor} de {codigos}.")
            id_sensor, id_cont = fila[0]
            lecturas = lecturas_de_falla(falla, tipo_sensor, ahora,
                                         umbral(vigentes, "lecturas_congeladas", "MAX", 6),
                                         umbral(vigentes, "salto_temperatura", "MAX", 10.0))
            for fecha, valores in lecturas:
                registrar_lectura_db(id_sensor, id_cont, fecha_hora=fecha, **valores)
            c.nota(f"Cassandra: sensor {id_sensor} ({codigo}): {len(lecturas)} lectura(s) "
                   f"con falla '{falla}'.")

        # 3. Revisión periódica: sin transmisión + umbrales + fallas, con mensajes.
        revision = ejecutar_revision_sensores()
        lecturas = revision["lecturas"]
        c.nota(f"MongoDB: revisión de sensores: {revision['alertas_procesadas']} alertas de "
               f"sin transmisión; {lecturas['fallas']} fallas de sensor y "
               f"{lecturas['anomalias']} anomalías de carga; {lecturas['alertas_nuevas']} "
               f"alertas nuevas y {lecturas['mensajes']} mensajes; errores: "
               f"{len(revision['errores']) + len(lecturas['errores'])}.")

        # 4. Predicción diaria con clima e historial de rutas.
        predicciones = ejecutar_predicciones_diarias()
        c.nota(f"MongoDB: {predicciones['guardadas']} predicciones (v4), "
               f"{predicciones['riesgos_altos']} de riesgo alto, errores: {predicciones['errores']}.")

    # 5. Reporte cobrable predictivo del cliente (se factura al generarse).
    usuario, cliente, tipo, formato = REPORTE_PREDICTIVO
    r = cobrables.solicitar_reporte(c.ids["cliente"][cliente], c.ids["usuario"][usuario],
                                    tipo, formato, {})
    c.nota(f"Reporte {r['id_reporte']} {tipo} {formato} para {cliente}: {r['estado']} "
           f"({r['filas']} filas, factura {r['id_factura']}).")

    # 6. Sesión de un usuario de cliente cerrada por el administrador.
    id_sesion = sesion_repository.iniciar_sesion_db(c.ids["usuario"][SESION_DEMO])
    if not sesion_repository.cerrar_sesion_ajena_db(id_sesion, ADMIN):
        raise RuntimeError("No se pudo cerrar la sesión de ejemplo.")
    c.nota(f"Sesión {id_sesion} del usuario de {SESION_DEMO} cerrada por el administrador.")


def dia3b_cargado():
    from app.database.mongo_connection import get_mongo_database
    ubicacion, fenomeno, _, _, _, descripcion = ALERTAS_CLIMA[0]
    return get_mongo_database()["alertas_climaticas"].find_one(
        {"ubicacion": ubicacion, "fenomeno": fenomeno, "descripcion": descripcion}) is not None


def reconstruir_ids(c):
    """IDs de una carga ya hecha en PostgreSQL (para reanudar o refrescar)."""
    for k, datos in {**CLIENTES_ARGENTINOS, **CLIENTES}.items():
        c.ids["cliente"][k] = q("SELECT id_cliente FROM cliente WHERE cuit = %s", (datos[1],))[0][0]
    for k, datos in OPERADORES.items():
        c.ids["operador"][k] = q("SELECT id_operador FROM operador_logistico WHERE cuit = %s",
                                 (datos[1],))[0][0]
    for k, datos in PROVEEDORES.items():
        c.ids["proveedor"][k] = q("SELECT id_proveedor FROM proveedor WHERE cuit = %s",
                                  (datos[1],))[0][0]
    for k, (_, ident, _) in VEHICULOS.items():
        c.ids["vehiculo"][k] = q("SELECT id_vehiculo FROM vehiculo WHERE identificacion = %s",
                                 (ident,))[0][0]
    codigos = {v[0]: k for k, v in CONTENEDORES.items()}
    for codigo, id_cont in q("SELECT codigo_internacional, id_contenedor FROM contenedor "
                             "WHERE codigo_internacional = ANY(%s)", (list(codigos),)):
        k = codigos[codigo]
        c.ids["contenedor"][k] = id_cont
        c.ids["sensor"][k] = dict(q("SELECT tipo, id_sensor FROM sensor_iot "
                                    "WHERE id_contenedor = %s", (id_cont,)))
    for k, e in ENVIOS.items():
        fila = q("SELECT id_envio FROM envio WHERE origen = %s AND destino = %s "
                 "AND fecha_creacion = %s", (e["origen"], e["destino"], t(e["creado"])))
        if len(fila) != 1:
            raise RuntimeError(f"No se identifica unívocamente el envío {k}.")
        c.ids["envio"][k] = fila[0][0]
    emails = {email: k for _, _, email, _, k in USUARIOS}
    for email, id_u in q("SELECT email, id_usuario FROM usuario WHERE email = ANY(%s)",
                         (list(emails),)):
        c.ids["usuario"][emails[email]] = id_u
    faltan = [k for k in CONTENEDORES if k not in c.ids["contenedor"]] + \
             [k for _, _, _, _, k in USUARIOS if k not in c.ids["usuario"]]
    if faltan:
        raise RuntimeError(f"Faltan datos de la carga en PostgreSQL: {faltan}")


# ------------------------------------------------------------------ main

def main(argv=None):
    p = argparse.ArgumentParser(description="Carga única de datos de ejemplo.")
    p.add_argument("--base", required=True, help="Nombre de la base PostgreSQL esperada.")
    p.add_argument("--solo-postgres", action="store_true",
                   help="Solo PostgreSQL (para una base descartable): no toca MongoDB, Cassandra ni Neo4j.")
    p.add_argument("--refrescar-lecturas", action="store_true",
                   help="Solo lecturas recientes, alertas y predicciones (para mostrar datos actuales).")
    p.add_argument("--dia3", action="store_true",
                   help="Agrega datos adicionales: países de los envíos, envío demorado, partidas "
                        "de carga, incidentes y reportes cobrables. Carga única.")
    p.add_argument("--dia3b", action="store_true",
                   help="Agrega datos adicionales: alertas climáticas, fallas de sensor, alertas "
                        "con mensajes, predicciones, reporte predictivo y cierre de una sesión. "
                        "Requiere --dia3. Carga única.")
    p.add_argument("--reanudar-nosql", action="store_true",
                   help="Completa MongoDB, Cassandra y Neo4j si la carga se cortó después "
                        "de PostgreSQL (no duplica lo ya cargado).")
    args = p.parse_args(argv)

    base = q("SELECT current_database()")[0][0]
    if base != args.base:
        sys.exit(f"La conexión apunta a '{base}', no a '{args.base}'. No se escribe nada.")
    if datetime.now(AR) < INICIO_MINIMO:
        sys.exit("Los datos usan fechas hasta el 30/10/2026 12:00; correr después de esa hora.")

    cargado = q("SELECT 1 FROM operador_logistico WHERE cuit = %s", (OPERADORES["ANDINOS"][1],))
    c = Carga(args.solo_postgres)

    if args.refrescar_lecturas:
        if not cargado:
            sys.exit("Primero hay que hacer la carga completa.")
        codigos = [CONTENEDORES[k][0] for k in ("C9", "C10", "C11")]
        conts = q("SELECT codigo_internacional, id_contenedor FROM contenedor "
                  "WHERE codigo_internacional = ANY(%s)", (codigos,))
        mapa = dict(conts)
        for kc, codigo in zip(("C9", "C10", "C11"), codigos):
            c.ids["contenedor"][kc] = mapa[codigo]
            c.ids["sensor"][kc] = dict(q("SELECT tipo, id_sensor FROM sensor_iot "
                                         "WHERE id_contenedor = %s", (mapa[codigo],)))
        cargar_lecturas_recientes(c)
        detectar_alertas_y_predicciones(c, list(mapa.values()))
        return 0

    if args.dia3:
        if not cargado:
            sys.exit("Primero hay que hacer la carga completa.")
        if _id_envio_por_clave(ENVIO_DEMORADO):
            sys.exit("Los datos de --dia3 ya están cargados (carga única). No se escribe nada.")
        reconstruir_ids(c)
        print(f"Base: {base} | modo: --dia3"
              f"{' (solo PostgreSQL)' if args.solo_postgres else ''}\n")
        cargar_dia3(c)
        print("\nDatos de --dia3 cargados.")
        return 0

    if args.dia3b:
        if not cargado or not _id_envio_por_clave(ENVIO_DEMORADO):
            sys.exit("Primero hay que hacer la carga completa y la de --dia3.")
        if q("SELECT 1 FROM reporte WHERE tipo = 'PREDICTIVO'"):
            sys.exit("Los datos de --dia3b ya están cargados (carga única). No se escribe nada.")
        if not args.solo_postgres and dia3b_cargado():
            sys.exit("Las alertas climáticas de --dia3b ya existen (carga única). No se escribe nada.")
        reconstruir_ids(c)
        print(f"Base: {base} | modo: --dia3b"
              f"{' (solo PostgreSQL)' if args.solo_postgres else ''}\n")
        cargar_dia3b(c)
        print("\nDatos de --dia3b cargados.")
        return 0

    if args.reanudar_nosql:
        if not cargado:
            sys.exit("No hay carga de PostgreSQL para reanudar.")
        reconstruir_ids(c)
        print(f"Base: {base} | modo: reanudar MongoDB, Cassandra y Neo4j\n")
        cargar_lecturas_historicas(c, saltar_existentes=True)
        cargar_lecturas_recientes(c)
        cargar_mensajes(c)
        sincronizar_grafo(c)
        detectar_alertas_y_predicciones(c, list(c.ids["contenedor"].values()))
        print("\nCarga reanudada y terminada.")
        return 0

    if cargado:
        sys.exit("Los datos de ejemplo ya están cargados (carga única). No se escribe nada.")

    clave = pedir_contrasena()
    print(f"Base: {base} | modo: {'solo PostgreSQL' if args.solo_postgres else 'completo'}\n")
    cargar_maestros(c, clave)
    cargar_precios(c)
    cargar_envios(c)
    cargar_facturacion(c)        # crea las cuentas de los clientes nuevos
    cargar_aperturas(c)
    cargar_cuentas_terceros(c)
    if not args.solo_postgres:
        cargar_lecturas_historicas(c)
        cargar_lecturas_recientes(c)
        cargar_mensajes(c)
        sincronizar_grafo(c)
        detectar_alertas_y_predicciones(c, list(c.ids["contenedor"].values()))
    print("\nCarga terminada.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
