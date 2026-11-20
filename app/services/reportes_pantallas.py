"""Pantallas de reportes: menú interno "Reportes" y "Mis reportes" del portal."""

from datetime import date, datetime, timedelta
from pathlib import Path

from app.repositories import reportes_repository as repo  # consultas de reportes en PostgreSQL
from app.repositories.facturacion_repository import listar_clientes_facturacion  # clientes para elegir en los filtros
from app.services import reportes_cobrables_service as cobrables  # lógica de los reportes que se facturan
from app.services import reportes_service as rs  # los reportes internos: cada uno devuelve una Tabla
from app.services.autenticacion import obtener_sesion_actual, parte_de, solo_internos  # sesión y controles de acceso
from app.utils.exportar_reportes import (  # mostrar, exportar y textos de las tablas
    CARPETA_REPORTES,
    escribir_csv,
    imprimir_tabla,
    mensaje_vacio,
    texto,
)
from app.utils import formato
from app.utils.errores import mensaje_error
from app.services.autenticacion import requiere_permiso  # cada pantalla verifica el permiso por su cuenta


def pausar():
    input("\nPresioná Enter para continuar...")


def pedir_fecha(mensaje, por_defecto):  # pide una fecha AAAA-MM-DD; Enter usa la sugerida. La usa pedir_periodo
    while True:
        valor = input(f"{mensaje} AAAA-MM-DD [Enter = {por_defecto}]: ").strip()
        if not valor:
            return por_defecto
        try:
            return date.fromisoformat(valor)  # si no es una fecha real, se vuelve a pedir
        except ValueError:
            print("Formato inválido.")


def pedir_periodo():  # pide desde y hasta; la usan los reportes internos con período y pedir_solicitud
    hoy = cobrables.hoy()  # fecha de hoy en Argentina
    while True:
        desde = pedir_fecha("Desde", hoy - timedelta(days=183))  # por defecto, los últimos seis meses
        hasta = pedir_fecha("Hasta", hoy)
        if desde <= hasta:  # si el período está al revés, se vuelve a pedir
            return desde, hasta
        print("La fecha 'desde' no puede ser posterior a 'hasta'. Ingresá el período de nuevo.")


def elegir_cliente(obligatorio=False):  # muestra los clientes y pide uno; la usan _ejecutar (opcional) y generar_para_cliente_service (obligatorio)
    clientes = listar_clientes_facturacion()  # clientes desde PostgreSQL
    for c in clientes:
        print(f"  {c[0]}. {c[1]}")
    texto_pedido = "ID del cliente: " if obligatorio else "ID del cliente (Enter = todos): "
    while True:
        valor = input(texto_pedido).strip()
        if not valor and not obligatorio:  # Enter = todos los clientes, si el filtro es opcional
            return None
        if valor.isdigit() and int(valor) in {c[0] for c in clientes}:  # solo acepta un ID de la lista
            return int(valor)
        print("Elegí un cliente de la lista.")


def mostrar_y_ofrecer_csv(tabla, vacio=None):  # muestra la tabla y ofrece guardarla en CSV; la usa _ejecutar en todos los reportes internos
    imprimir_tabla(tabla, vacio)
    if tabla.filas and input("\n¿Exportar a CSV? (S/N): ").strip().upper() == "S":  # solo ofrece exportar si hay filas
        nombre = f"{datetime.now():%Y%m%d_%H%M%S}_{tabla.titulo[:40]}"  # nombre con fecha y hora más el título
        nombre = "".join(ch if ch.isalnum() else "_" for ch in nombre)  # cambia los caracteres raros por guion bajo
        ruta = escribir_csv(tabla, Path(CARPETA_REPORTES) / "internos" / f"{nombre}.csv")  # lo guarda en reportes_generados/internos
        print(f"Exportado: {ruta}")


# ------------------------------------------------ reportes internos

def _ejecutar(constructor, con_periodo=True, con_cliente=True):  # corre un reporte interno: pide filtros, arma la Tabla y la muestra; lo usan todas las opciones de los submenús
    try:
        argumentos = []  # argumentos para la función del reporte, en orden
        if con_periodo:  # los reportes con período piden desde y hasta
            argumentos += list(pedir_periodo())
        cliente = None
        if con_cliente:  # los que filtran por cliente piden uno (Enter = todos)
            cliente = elegir_cliente()
            argumentos.append(cliente)
        tabla = constructor(*argumentos)  # llama al reporte de reportes_service, que consulta las bases
        mostrar_y_ofrecer_csv(tabla, mensaje_vacio(tabla, cliente=cliente is not None,  # si no hay filas, el mensaje aclara el cliente y el período
                                                   periodo=con_periodo))
    except Exception as error:  # cualquier error se muestra traducido
        print(f"\nError al generar el reporte: {mensaje_error(error)}")
    finally:
        pausar()


REPORTES_OPERATIVOS = {  # opción 1 del menú Reportes
    "1": ("Envíos por país de destino", lambda: _ejecutar(rs.reporte_envios_por_pais)),  # envíos por país de destino, con período y cliente
    "2": ("Envíos por estado", lambda: _ejecutar(rs.reporte_envios_por_estado)),  # cantidad de envíos de cada estado
    "3": ("Envíos por cliente", lambda: _ejecutar(rs.reporte_envios_por_cliente)),  # envíos de cada cliente, por estado
    "4": ("Envíos demorados", lambda: _ejecutar(rs.reporte_envios_demorados, con_periodo=False)),  # en curso con la llegada estimada vencida (sin período)
    "5": ("Incidentes abiertos", lambda: _ejecutar(rs.reporte_incidentes_abiertos, con_periodo=False)),  # incidentes sin cerrar (sin período)
}
REPORTES_ANALITICOS = {  # opción 2 del menú Reportes
    "1": ("Tiempos máximos y mínimos de envío por cliente",  # horas mínimas y máximas por cliente
          lambda: _ejecutar(rs.reporte_tiempos_extremos)),
    "2": ("Promedio de incidentes por país / estado / cliente",  # incidentes por envío según tres agrupaciones
          lambda: _ejecutar(rs.reporte_promedio_incidentes)),
    "3": ("Tiempos promedio de entrega", lambda: _ejecutar(rs.reporte_tiempos_promedio)),  # horas promedio por cliente, ruta y medio
    "4": ("Costos por tipo de transporte (cobrado vs costo de operadores)",  # facturado vs. costo de operadores, sin filtro de cliente
          lambda: _ejecutar(rs.reporte_costos_por_medio, con_cliente=False)),
}
REPORTES_RANKINGS = {  # opción 3 del menú Reportes
    "1": ("Rutas con más incidentes", lambda: _ejecutar(rs.reporte_ranking_rutas, con_cliente=False)),  # rutas ordenadas por cantidad de incidentes
    "2": ("Clientes por volumen transportado",  # clientes ordenados por peso y capacidad
          lambda: _ejecutar(rs.reporte_ranking_volumen, con_cliente=False)),
    "3": ("Desempeño histórico (a tiempo vs tarde por ruta, operador y mes)",  # a tiempo vs. tarde por ruta, operador y mes
          lambda: _ejecutar(rs.reporte_desempeno)),
}
REPORTES_PREDICTIVOS = {  # opción 5 del menú Reportes
    "1": ("Riesgo de demora de los envíos en curso",  # última predicción de cada envío en curso
          lambda: _ejecutar(rs.reporte_riesgo_envios, con_periodo=False)),
    "2": ("Rutas que suelen atrasarse",  # historial de atrasos por ruta
          lambda: _ejecutar(rs.reporte_rutas_atraso, con_periodo=False, con_cliente=False)),
    "3": ("Alertas climáticas vigentes y envíos afectados",  # alertas de clima y qué envíos tocan
          lambda: _ejecutar(rs.reporte_clima_vigente, con_periodo=False, con_cliente=False)),
}


@requiere_permiso(1)  # nivel 1 para los submenús internos
def submenu(titulo, opciones):  # submenú de reportes internos; lo abren las opciones 1 a 5 del menú Reportes
    """Submenú de reportes internos."""
    _menu(titulo, opciones)


def _menu(titulo, opciones):  # muestra un submenú a partir de un diccionario; lo usan submenu y "Mis reportes" del portal
    """Muestra un submenú; cada opción verifica sus propios permisos."""
    while True:
        print(f"\n--- {titulo} ---")
        for clave, (nombre, _) in opciones.items():  # arma el menú con los nombres del diccionario
            print(f"{clave}. {nombre}")
        print("0. Volver")
        opcion = input("Opción: ").strip()
        if opcion == "0":
            return
        if opcion in opciones:  # ejecuta la función de la opción elegida
            opciones[opcion][1]()
        else:
            print("Opción inválida.")


# ------------------------------------------------ reportes cobrables

def nombre_tipo(codigo):  # nombre legible de un tipo de reporte cobrable; lo usan mostrar_reporte y el listado
    """Nombre del tipo de reporte para mostrar (el código es interno)."""
    try:
        nombres = {t[0]: t[1] for t in repo.listar_tipos_reporte(solo_activos=False)}  # código -> nombre, desde la tabla tipo_reporte
    except Exception:  # si falla la consulta, se muestra el código
        nombres = {}
    return nombres.get(codigo, codigo)

def mostrar_reporte(reporte):  # imprime los datos de un reporte cobrable; lo usan ver_reporte_service y _resultado
    print(f"\nReporte N.º {reporte['id_reporte']} | {reporte['cliente']} | {nombre_tipo(reporte['tipo'])} | "
          f"{reporte['formato']} | {reporte['estado']}")
    print(f"Pedido por {reporte['usuario']} el {texto(reporte['fecha_solicitud'])}")
    for linea in cobrables.describir_parametros(reporte["parametros"]):  # filtros con que se pidió (período, contenedor)
        print(f"  {linea}")
    print(f"Precio: {formato.dinero(reporte['importe_base'])} + IVA"
          + (f" | Factura N.º {reporte['id_factura']} por {formato.dinero(reporte['total_factura'])}"
             if reporte["id_factura"] else ""))  # si ya se facturó, agrega la factura
    if reporte["archivo"]:
        # Solo el nombre del archivo: la ruta en el servidor no le sirve al usuario.
        print(f"Archivo: {Path(reporte['archivo']).name} ({reporte['filas']} filas)")
    if reporte["error"]:  # el motivo, si no se pudo generar
        print(f"Error: {reporte['error']}")


def _vista_previa(reporte, lineas=25):  # muestra las primeras líneas del CSV generado; la usan ver_reporte_service y _resultado
    if reporte["archivo"] and reporte["archivo"].lower().endswith(".csv") and Path(reporte["archivo"]).exists():  # solo si es un CSV que todavía existe en la carpeta
        print("\nContenido:")
        with open(reporte["archivo"], encoding="utf-8-sig") as archivo:
            for numero, linea in enumerate(archivo):
                if numero >= lineas:  # corta después de 25 líneas
                    print("...")
                    break
                print("  " + linea.rstrip())


def pedir_solicitud():  # pide tipo, filtros y formato de un reporte cobrable; la usan el pedido interno y el del portal
    """Tipo, formato y parámetros del reporte. Devuelve (tipo, formato, params) o None."""
    tipos = repo.listar_tipos_reporte()  # tipos activos con su precio, desde PostgreSQL
    print("\nTipos de reporte (precio + IVA):")
    for numero, t in enumerate(tipos, 1):
        print(f"  {numero}. {t[1]} - {formato.dinero(t[4])}")
        print(f"     {t[2]}")
    eleccion = input("Tipo (0 = cancelar): ").strip()
    if not eleccion.isdigit() or not 1 <= int(eleccion) <= len(tipos):  # cualquier otra respuesta cancela
        return None
    tipo = tipos[int(eleccion) - 1]
    params = {}
    if tipo[0] in cobrables.SIN_PERIODO:  # el predictivo es sobre hoy, no pide período
        print("Muestra la situación de hoy de tus envíos en curso.")
    else:
        desde, hasta = pedir_periodo()
        params = {"desde": desde.isoformat(), "hasta": hasta.isoformat()}
    for nombre, (descripcion, _) in cobrables.EXTRAS[tipo[0]].items():  # filtros propios de cada tipo (severidad, estado, ruta, contenedor)
        if nombre == "id_contenedor":  # el contenedor se pide por código y se guarda el ID
            params[nombre] = pedir_contenedor()
            continue
        params[nombre] = input(f"{descripcion} (Enter = sin filtro): ").strip()
    while True:  # pide el formato hasta que sea CSV o PDF
        formato_archivo = input("Formato (CSV/PDF) [Enter = CSV]: ").strip().upper() or "CSV"
        if formato_archivo in cobrables.FORMATOS:
            break
        print("Elegí CSV o PDF.")
    print(f"\nSe facturará {formato.dinero(tipo[4])} + IVA a la cuenta corriente al generarse.")
    if input("¿Confirmar? (S/N): ").strip().upper() != "S":  # sin confirmar no se pide (porque se factura)
        return None
    return tipo[0], formato_archivo, params


def pedir_contenedor():  # pide el código de un contenedor y devuelve su ID; la usa pedir_solicitud
    """Código del contenedor -> id (Enter = todos). El reporte filtra por cliente."""
    from app.repositories.contenedor_repository import buscar_contenedor_por_codigo  # se importa acá porque solo hace falta en este caso
    while True:
        codigo = input("Código de contenedor, ej. MSCU1234571 (Enter = todos): ").strip().upper()
        if not codigo:  # Enter = todos los contenedores
            return ""
        contenedor = buscar_contenedor_por_codigo(codigo)  # busca el código en PostgreSQL
        if contenedor:
            return contenedor[0]
        print("No existe un contenedor con ese código.")


def _resultado(reporte):  # muestra cómo terminó un pedido de reporte cobrable; la usan el pedido interno y el del portal
    mostrar_reporte(reporte)
    if reporte["estado"] == "FACTURADO":  # se generó y se facturó
        print("\nReporte generado y facturado.")
        _vista_previa(reporte)
    elif reporte["estado"] == "GENERADO":  # se generó pero la factura quedó pendiente
        print("\nReporte generado; la facturación quedó pendiente (se reintenta desde Facturación).")
    else:  # ERROR: no se generó y no se factura
        print("\nNo se pudo generar el reporte; no se facturó.")


@requiere_permiso(3)  # nivel 3, como la opción 4 del menú Reportes
@solo_internos  # solo usuarios internos
def generar_para_cliente_service():  # un interno pide un reporte cobrable para un cliente; opción 1 de Reportes cobrables
    print("\n--- GENERAR REPORTE COBRABLE PARA UN CLIENTE ---")
    try:
        id_cliente = elegir_cliente(obligatorio=True)  # acá el cliente es obligatorio
        solicitud = pedir_solicitud()
        if solicitud is None:
            print("Cancelado.")
            return
        tipo, formato_archivo, params = solicitud
        _resultado(cobrables.solicitar_reporte(  # crea el pedido, genera el archivo y lo factura a la cuenta del cliente
            id_cliente, obtener_sesion_actual()["id_usuario"], tipo, formato_archivo, params))
    except Exception as error:
        print(f"\nError: {mensaje_error(error)}")
    finally:
        pausar()


@requiere_permiso(3, portal=("CLIENTE",), portal_con_dato=True)  # interno de nivel 3, o un cliente desde el portal con su propio id
def listar_reportes_service(id_cliente=None):  # lista los reportes cobrables; opción 2 de Reportes cobrables y "Mis reportes" del portal
    print("\n--- REPORTES COBRABLES ---")
    try:
        reportes = repo.listar_reportes(id_cliente)  # sin cliente trae todos; con cliente, solo los suyos
        if not reportes:
            print("No hay reportes.")
        for r in reportes:
            factura = f"factura N.º {r['id_factura']}" if r["id_factura"] else "sin factura"  # si ya se facturó o no
            print(f"  {r['id_reporte']} | {texto(r['fecha_solicitud'])} | {r['cliente']} | "
                  f"{nombre_tipo(r['tipo'])} | {r['formato']} | {r['estado']} | {factura}")
    except Exception as error:
        print(f"Error: {mensaje_error(error)}")
    finally:
        pausar()


@requiere_permiso(3, portal=("CLIENTE",), portal_con_dato=True)  # interno de nivel 3, o un cliente desde el portal con su propio id
def ver_reporte_service(id_cliente=None):  # muestra un reporte por número; opción 3 de Reportes cobrables y "Ver uno de mis reportes" del portal
    """Interno: cualquier reporte. Portal: id_cliente fijo (los ajenos 'no existen')."""
    try:
        numero = input("N.º de reporte: ").strip()
        if not numero.isdigit():  # el número tiene que ser entero
            print("Número inválido.")
            return
        reporte = (repo.obtener_reporte(int(numero)) if id_cliente is None  # un interno ve cualquiera; un cliente, solo los suyos
                   else cobrables.reporte_del_cliente(int(numero), id_cliente))
        if reporte is None:  # un reporte de otro cliente se trata como si no existiera
            print("No existe un reporte con ese número"
                  + (" entre tus reportes." if id_cliente is not None else "."))
            return
        mostrar_reporte(reporte)
        _vista_previa(reporte)
    except Exception as error:
        print(f"Error: {mensaje_error(error)}")
    finally:
        pausar()


REPORTES_COBRABLES = {  # opción 4 del menú Reportes (nivel 3)
    "1": ("Generar reporte para un cliente", generar_para_cliente_service),  # pedir un reporte para un cliente
    "2": ("Listar reportes", listar_reportes_service),  # todos los reportes cobrables
    "3": ("Ver un reporte", ver_reporte_service),  # detalle y vista previa de uno
}


@requiere_permiso(3)  # nivel 3, como facturación
@solo_internos  # solo usuarios internos
def facturar_reportes_pendientes_service():  # factura los reportes generados que quedaron sin factura; opción 12 del menú de facturación
    print("\n--- FACTURAR REPORTES GENERADOS PENDIENTES ---")
    try:
        facturados, errores = cobrables.facturar_pendientes()  # intenta facturar cada reporte GENERADO
        print(f"Facturados: {len(facturados)}")
        for f in facturados:
            print(f"  Reporte {f['id_reporte']} -> factura {f['id_factura']} por {formato.dinero(f['total'])}")
        for id_reporte, error in errores:  # los que no se pudieron facturar, con el motivo ya traducido
            print(f"  Reporte {id_reporte}: {error}")
    except Exception as error:
        print(f"Error: {mensaje_error(error)}")
    finally:
        pausar()


@requiere_permiso(3)  # nivel 3, como facturación
@solo_internos  # solo usuarios internos
def precios_reportes_service():  # lista y cambia el precio de los reportes cobrables; opción 13 del menú de facturación
    print("\n--- PRECIOS DE REPORTES (ARS, sin IVA) ---")
    try:
        tipos = repo.listar_tipos_reporte(solo_activos=False)  # todos los tipos, activos o no
        for numero, t in enumerate(tipos, 1):
            print(f"  {numero}. {t[1]:<45} {formato.dinero(t[4]):>12} {'activo' if t[5] else 'inactivo'}")
        eleccion = input("\nNúmero a modificar (Enter = ninguno): ").strip()
        if not eleccion:  # Enter = no cambia nada
            return
        if not eleccion.isdigit() or not 1 <= int(eleccion) <= len(tipos):
            print("Número inválido.")
            return
        codigo = tipos[int(eleccion) - 1][0]  # código del tipo elegido
        from decimal import Decimal, InvalidOperation
        try:
            precio = Decimal(input("Nuevo precio: ").strip().replace(",", "."))  # acepta coma o punto decimal
        except InvalidOperation:
            print("Precio inválido.")
            return
        if not precio.is_finite() or precio <= 0 or precio != precio.quantize(Decimal("0.01")):  # mayor a cero y con hasta dos decimales
            print("El precio debe ser mayor a cero y con hasta 2 decimales.")
            return
        repo.actualizar_precio_tipo_reporte(codigo, precio, obtener_sesion_actual()["id_usuario"])  # guarda el precio nuevo y quién lo cambió
        print("Precio actualizado. Rige para los reportes que se pidan desde ahora.")
    except Exception as error:
        print(f"Error: {mensaje_error(error)}")
    finally:
        pausar()


# ------------------------------------------------ portal: "Mis reportes"

def _cliente_de_la_sesion():  # id del cliente del usuario conectado; la usan las opciones de "Mis reportes"
    tipo, id_cliente = parte_de(obtener_sesion_actual())
    if tipo != "CLIENTE":  # solo para usuarios de un cliente
        raise PermissionError("Esta opción es para usuarios de clientes.")
    return id_cliente


def solicitar_mi_reporte_service():  # el cliente pide un reporte cobrable sobre sus datos; opción 2 de "Mis reportes" en el portal
    print("\n--- SOLICITAR UN REPORTE ---")
    try:
        id_cliente = _cliente_de_la_sesion()  # el cliente sale de la sesión, no se elige
        solicitud = pedir_solicitud()
        if solicitud is None:
            print("Cancelado.")
            return
        tipo, formato_archivo, params = solicitud
        _resultado(cobrables.solicitar_reporte(  # lo genera y lo factura a su cuenta corriente
            id_cliente, obtener_sesion_actual()["id_usuario"], tipo, formato_archivo, params))
    except Exception as error:
        print(f"\nError: {mensaje_error(error)}")
    finally:
        pausar()


def listar_mis_reportes_service():  # lista los reportes del cliente conectado; opción 1 de "Mis reportes"
    try:
        id_cliente = _cliente_de_la_sesion()
    except PermissionError as error:
        print(f"\n{mensaje_error(error)}")
        pausar()
        return
    listar_reportes_service(id_cliente)  # reutiliza el listado, filtrado por su cliente


def ver_mi_reporte_service():  # muestra uno de los reportes del cliente conectado; opción 3 de "Mis reportes"
    try:
        id_cliente = _cliente_de_la_sesion()
    except PermissionError as error:
        print(f"\n{mensaje_error(error)}")
        pausar()
        return
    ver_reporte_service(id_cliente)  # reutiliza la vista, filtrada por su cliente


MIS_REPORTES = {  # opciones de "Mis reportes" en el portal del cliente
    "1": ("Mis reportes", listar_mis_reportes_service),  # listar los reportes del cliente
    "2": ("Solicitar un reporte (se factura)", solicitar_mi_reporte_service),  # pedir uno nuevo
    "3": ("Ver uno de mis reportes", ver_mi_reporte_service),  # ver el detalle de uno
}


def mis_reportes_menu():  # submenú "Mis reportes"; opción 9 del portal del cliente
    # Portal del cliente: sus opciones filtran por el cliente de la sesión.
    _menu("MIS REPORTES", MIS_REPORTES)
