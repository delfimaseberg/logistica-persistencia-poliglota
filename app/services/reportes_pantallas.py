"""Pantallas de reportes: menú interno "Reportes" y "Mis reportes" del portal."""

from datetime import date, datetime, timedelta
from pathlib import Path

from app.repositories import reportes_repository as repo
from app.repositories.facturacion_repository import listar_clientes_facturacion
from app.services import reportes_cobrables_service as cobrables
from app.services import reportes_service as rs
from app.services.autenticacion import obtener_sesion_actual, parte_de, solo_internos
from app.utils.exportar_reportes import (
    CARPETA_REPORTES,
    escribir_csv,
    imprimir_tabla,
    mensaje_vacio,
    texto,
)
from app.utils import formato
from app.utils.errores import mensaje_error
from app.services.autenticacion import requiere_permiso


def pausar():
    input("\nPresioná Enter para continuar...")


def pedir_fecha(mensaje, por_defecto):
    while True:
        valor = input(f"{mensaje} AAAA-MM-DD [Enter = {por_defecto}]: ").strip()
        if not valor:
            return por_defecto
        try:
            return date.fromisoformat(valor)
        except ValueError:
            print("Formato inválido.")


def pedir_periodo():
    hoy = cobrables.hoy()
    while True:
        desde = pedir_fecha("Desde", hoy - timedelta(days=183))
        hasta = pedir_fecha("Hasta", hoy)
        if desde <= hasta:
            return desde, hasta
        print("La fecha 'desde' no puede ser posterior a 'hasta'. Ingresá el período de nuevo.")


def elegir_cliente(obligatorio=False):
    clientes = listar_clientes_facturacion()
    for c in clientes:
        print(f"  {c[0]}. {c[1]}")
    texto_pedido = "ID del cliente: " if obligatorio else "ID del cliente (Enter = todos): "
    while True:
        valor = input(texto_pedido).strip()
        if not valor and not obligatorio:
            return None
        if valor.isdigit() and int(valor) in {c[0] for c in clientes}:
            return int(valor)
        print("Elegí un cliente de la lista.")


def mostrar_y_ofrecer_csv(tabla, vacio=None):
    imprimir_tabla(tabla, vacio)
    if tabla.filas and input("\n¿Exportar a CSV? (S/N): ").strip().upper() == "S":
        nombre = f"{datetime.now():%Y%m%d_%H%M%S}_{tabla.titulo[:40]}"
        nombre = "".join(ch if ch.isalnum() else "_" for ch in nombre)
        ruta = escribir_csv(tabla, Path(CARPETA_REPORTES) / "internos" / f"{nombre}.csv")
        print(f"Exportado: {ruta}")


# ------------------------------------------------ reportes internos

def _ejecutar(constructor, con_periodo=True, con_cliente=True):
    try:
        argumentos = []
        if con_periodo:
            argumentos += list(pedir_periodo())
        cliente = None
        if con_cliente:
            cliente = elegir_cliente()
            argumentos.append(cliente)
        tabla = constructor(*argumentos)
        mostrar_y_ofrecer_csv(tabla, mensaje_vacio(tabla, cliente=cliente is not None,
                                                   periodo=con_periodo))
    except Exception as error:
        print(f"\nError al generar el reporte: {mensaje_error(error)}")
    finally:
        pausar()


REPORTES_OPERATIVOS = {
    "1": ("Envíos por país de destino", lambda: _ejecutar(rs.reporte_envios_por_pais)),
    "2": ("Envíos por estado", lambda: _ejecutar(rs.reporte_envios_por_estado)),
    "3": ("Envíos por cliente", lambda: _ejecutar(rs.reporte_envios_por_cliente)),
    "4": ("Envíos demorados", lambda: _ejecutar(rs.reporte_envios_demorados, con_periodo=False)),
    "5": ("Incidentes abiertos", lambda: _ejecutar(rs.reporte_incidentes_abiertos, con_periodo=False)),
}
REPORTES_ANALITICOS = {
    "1": ("Tiempos máximos y mínimos de envío por cliente",
          lambda: _ejecutar(rs.reporte_tiempos_extremos)),
    "2": ("Promedio de incidentes por país / estado / cliente",
          lambda: _ejecutar(rs.reporte_promedio_incidentes)),
    "3": ("Tiempos promedio de entrega", lambda: _ejecutar(rs.reporte_tiempos_promedio)),
    "4": ("Costos por tipo de transporte (cobrado vs costo de operadores)",
          lambda: _ejecutar(rs.reporte_costos_por_medio, con_cliente=False)),
}
REPORTES_RANKINGS = {
    "1": ("Rutas con más incidentes", lambda: _ejecutar(rs.reporte_ranking_rutas, con_cliente=False)),
    "2": ("Clientes por volumen transportado",
          lambda: _ejecutar(rs.reporte_ranking_volumen, con_cliente=False)),
    "3": ("Desempeño histórico (a tiempo vs tarde por ruta, operador y mes)",
          lambda: _ejecutar(rs.reporte_desempeno)),
}
REPORTES_PREDICTIVOS = {
    "1": ("Riesgo de demora de los envíos en curso",
          lambda: _ejecutar(rs.reporte_riesgo_envios, con_periodo=False)),
    "2": ("Rutas que suelen atrasarse",
          lambda: _ejecutar(rs.reporte_rutas_atraso, con_periodo=False, con_cliente=False)),
    "3": ("Alertas climáticas vigentes y envíos afectados",
          lambda: _ejecutar(rs.reporte_clima_vigente, con_periodo=False, con_cliente=False)),
}


@requiere_permiso(1)
def submenu(titulo, opciones):
    """Submenú de reportes internos."""
    _menu(titulo, opciones)


def _menu(titulo, opciones):
    """Muestra un submenú; cada opción verifica sus propios permisos."""
    while True:
        print(f"\n--- {titulo} ---")
        for clave, (nombre, _) in opciones.items():
            print(f"{clave}. {nombre}")
        print("0. Volver")
        opcion = input("Opción: ").strip()
        if opcion == "0":
            return
        if opcion in opciones:
            opciones[opcion][1]()
        else:
            print("Opción inválida.")


# ------------------------------------------------ reportes cobrables

def nombre_tipo(codigo):
    """Nombre del tipo de reporte para mostrar (el código es interno)."""
    try:
        nombres = {t[0]: t[1] for t in repo.listar_tipos_reporte(solo_activos=False)}
    except Exception:
        nombres = {}
    return nombres.get(codigo, codigo)

def mostrar_reporte(reporte):
    print(f"\nReporte N.º {reporte['id_reporte']} | {reporte['cliente']} | {nombre_tipo(reporte['tipo'])} | "
          f"{reporte['formato']} | {reporte['estado']}")
    print(f"Pedido por {reporte['usuario']} el {texto(reporte['fecha_solicitud'])}")
    for linea in cobrables.describir_parametros(reporte["parametros"]):
        print(f"  {linea}")
    print(f"Precio: {formato.dinero(reporte['importe_base'])} + IVA"
          + (f" | Factura N.º {reporte['id_factura']} por {formato.dinero(reporte['total_factura'])}"
             if reporte["id_factura"] else ""))
    if reporte["archivo"]:
        # Solo el nombre del archivo: la ruta en el servidor no le sirve al usuario.
        print(f"Archivo: {Path(reporte['archivo']).name} ({reporte['filas']} filas)")
    if reporte["error"]:
        print(f"Error: {reporte['error']}")


def _vista_previa(reporte, lineas=25):
    if reporte["archivo"] and reporte["archivo"].lower().endswith(".csv") and Path(reporte["archivo"]).exists():
        print("\nContenido:")
        with open(reporte["archivo"], encoding="utf-8-sig") as archivo:
            for numero, linea in enumerate(archivo):
                if numero >= lineas:
                    print("...")
                    break
                print("  " + linea.rstrip())


def pedir_solicitud():
    """Tipo, formato y parámetros del reporte. Devuelve (tipo, formato, params) o None."""
    tipos = repo.listar_tipos_reporte()
    print("\nTipos de reporte (precio + IVA):")
    for numero, t in enumerate(tipos, 1):
        print(f"  {numero}. {t[1]} - {formato.dinero(t[4])}")
        print(f"     {t[2]}")
    eleccion = input("Tipo (0 = cancelar): ").strip()
    if not eleccion.isdigit() or not 1 <= int(eleccion) <= len(tipos):
        return None
    tipo = tipos[int(eleccion) - 1]
    params = {}
    if tipo[0] in cobrables.SIN_PERIODO:
        print("Muestra la situación de hoy de tus envíos en curso.")
    else:
        desde, hasta = pedir_periodo()
        params = {"desde": desde.isoformat(), "hasta": hasta.isoformat()}
    for nombre, (descripcion, _) in cobrables.EXTRAS[tipo[0]].items():
        if nombre == "id_contenedor":
            params[nombre] = pedir_contenedor()
            continue
        params[nombre] = input(f"{descripcion} (Enter = sin filtro): ").strip()
    while True:
        formato_archivo = input("Formato (CSV/PDF) [Enter = CSV]: ").strip().upper() or "CSV"
        if formato_archivo in cobrables.FORMATOS:
            break
        print("Elegí CSV o PDF.")
    print(f"\nSe facturará {formato.dinero(tipo[4])} + IVA a la cuenta corriente al generarse.")
    if input("¿Confirmar? (S/N): ").strip().upper() != "S":
        return None
    return tipo[0], formato_archivo, params


def pedir_contenedor():
    """Código del contenedor -> id (Enter = todos). El reporte filtra por cliente."""
    from app.repositories.contenedor_repository import buscar_contenedor_por_codigo
    while True:
        codigo = input("Código de contenedor, ej. MSCU1234571 (Enter = todos): ").strip().upper()
        if not codigo:
            return ""
        contenedor = buscar_contenedor_por_codigo(codigo)
        if contenedor:
            return contenedor[0]
        print("No existe un contenedor con ese código.")


def _resultado(reporte):
    mostrar_reporte(reporte)
    if reporte["estado"] == "FACTURADO":
        print("\nReporte generado y facturado.")
        _vista_previa(reporte)
    elif reporte["estado"] == "GENERADO":
        print("\nReporte generado; la facturación quedó pendiente (se reintenta desde Facturación).")
    else:
        print("\nNo se pudo generar el reporte; no se facturó.")


@requiere_permiso(3)
@solo_internos
def generar_para_cliente_service():
    print("\n--- GENERAR REPORTE COBRABLE PARA UN CLIENTE ---")
    try:
        id_cliente = elegir_cliente(obligatorio=True)
        solicitud = pedir_solicitud()
        if solicitud is None:
            print("Cancelado.")
            return
        tipo, formato_archivo, params = solicitud
        _resultado(cobrables.solicitar_reporte(
            id_cliente, obtener_sesion_actual()["id_usuario"], tipo, formato_archivo, params))
    except Exception as error:
        print(f"\nError: {mensaje_error(error)}")
    finally:
        pausar()


@requiere_permiso(3, portal=("CLIENTE",), portal_con_dato=True)
def listar_reportes_service(id_cliente=None):
    print("\n--- REPORTES COBRABLES ---")
    try:
        reportes = repo.listar_reportes(id_cliente)
        if not reportes:
            print("No hay reportes.")
        for r in reportes:
            factura = f"factura N.º {r['id_factura']}" if r["id_factura"] else "sin factura"
            print(f"  {r['id_reporte']} | {texto(r['fecha_solicitud'])} | {r['cliente']} | "
                  f"{nombre_tipo(r['tipo'])} | {r['formato']} | {r['estado']} | {factura}")
    except Exception as error:
        print(f"Error: {mensaje_error(error)}")
    finally:
        pausar()


@requiere_permiso(3, portal=("CLIENTE",), portal_con_dato=True)
def ver_reporte_service(id_cliente=None):
    """Interno: cualquier reporte. Portal: id_cliente fijo (los ajenos 'no existen')."""
    try:
        numero = input("N.º de reporte: ").strip()
        if not numero.isdigit():
            print("Número inválido.")
            return
        reporte = (repo.obtener_reporte(int(numero)) if id_cliente is None
                   else cobrables.reporte_del_cliente(int(numero), id_cliente))
        if reporte is None:
            print("No existe un reporte con ese número"
                  + (" entre tus reportes." if id_cliente is not None else "."))
            return
        mostrar_reporte(reporte)
        _vista_previa(reporte)
    except Exception as error:
        print(f"Error: {mensaje_error(error)}")
    finally:
        pausar()


REPORTES_COBRABLES = {
    "1": ("Generar reporte para un cliente", generar_para_cliente_service),
    "2": ("Listar reportes", listar_reportes_service),
    "3": ("Ver un reporte", ver_reporte_service),
}


@requiere_permiso(3)
@solo_internos
def facturar_reportes_pendientes_service():
    print("\n--- FACTURAR REPORTES GENERADOS PENDIENTES ---")
    try:
        facturados, errores = cobrables.facturar_pendientes()
        print(f"Facturados: {len(facturados)}")
        for f in facturados:
            print(f"  Reporte {f['id_reporte']} -> factura {f['id_factura']} por {formato.dinero(f['total'])}")
        for id_reporte, error in errores:
            print(f"  Reporte {id_reporte}: {error}")
    except Exception as error:
        print(f"Error: {mensaje_error(error)}")
    finally:
        pausar()


@requiere_permiso(3)
@solo_internos
def precios_reportes_service():
    print("\n--- PRECIOS DE REPORTES (ARS, sin IVA) ---")
    try:
        tipos = repo.listar_tipos_reporte(solo_activos=False)
        for numero, t in enumerate(tipos, 1):
            print(f"  {numero}. {t[1]:<45} {formato.dinero(t[4]):>12} {'activo' if t[5] else 'inactivo'}")
        eleccion = input("\nNúmero a modificar (Enter = ninguno): ").strip()
        if not eleccion:
            return
        if not eleccion.isdigit() or not 1 <= int(eleccion) <= len(tipos):
            print("Número inválido.")
            return
        codigo = tipos[int(eleccion) - 1][0]
        from decimal import Decimal, InvalidOperation
        try:
            precio = Decimal(input("Nuevo precio: ").strip().replace(",", "."))
        except InvalidOperation:
            print("Precio inválido.")
            return
        if not precio.is_finite() or precio <= 0 or precio != precio.quantize(Decimal("0.01")):
            print("El precio debe ser mayor a cero y con hasta 2 decimales.")
            return
        repo.actualizar_precio_tipo_reporte(codigo, precio, obtener_sesion_actual()["id_usuario"])
        print("Precio actualizado. Rige para los reportes que se pidan desde ahora.")
    except Exception as error:
        print(f"Error: {mensaje_error(error)}")
    finally:
        pausar()


# ------------------------------------------------ portal: "Mis reportes"

def _cliente_de_la_sesion():
    tipo, id_cliente = parte_de(obtener_sesion_actual())
    if tipo != "CLIENTE":
        raise PermissionError("Esta opción es para usuarios de clientes.")
    return id_cliente


def solicitar_mi_reporte_service():
    print("\n--- SOLICITAR UN REPORTE ---")
    try:
        id_cliente = _cliente_de_la_sesion()
        solicitud = pedir_solicitud()
        if solicitud is None:
            print("Cancelado.")
            return
        tipo, formato_archivo, params = solicitud
        _resultado(cobrables.solicitar_reporte(
            id_cliente, obtener_sesion_actual()["id_usuario"], tipo, formato_archivo, params))
    except Exception as error:
        print(f"\nError: {mensaje_error(error)}")
    finally:
        pausar()


def listar_mis_reportes_service():
    try:
        id_cliente = _cliente_de_la_sesion()
    except PermissionError as error:
        print(f"\n{mensaje_error(error)}")
        pausar()
        return
    listar_reportes_service(id_cliente)


def ver_mi_reporte_service():
    try:
        id_cliente = _cliente_de_la_sesion()
    except PermissionError as error:
        print(f"\n{mensaje_error(error)}")
        pausar()
        return
    ver_reporte_service(id_cliente)


MIS_REPORTES = {
    "1": ("Mis reportes", listar_mis_reportes_service),
    "2": ("Solicitar un reporte (se factura)", solicitar_mi_reporte_service),
    "3": ("Ver uno de mis reportes", ver_mi_reporte_service),
}


def mis_reportes_menu():
    # Portal del cliente: sus opciones filtran por el cliente de la sesión.
    _menu("MIS REPORTES", MIS_REPORTES)
