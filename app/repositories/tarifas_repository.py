"""Persistencia PostgreSQL de cargas, reglas y snapshots tarifarios."""

from app.database.postgres_connection import get_postgres_connection


def listar_envios_tarifables():  # envíos para elegir al cargar una partida; opción 2 del menú de tarifas
    with get_postgres_connection() as conn, conn.cursor() as cur:
        cur.execute("""SELECT id_envio, id_cliente, origen, destino, estado
                       FROM envio ORDER BY id_envio""")
        return cur.fetchall()


def listar_tipos_carga():  # categorías activas; las usan cargar partida y crear regla
    with get_postgres_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT codigo, descripcion FROM tipo_carga WHERE activo ORDER BY codigo")
        return cur.fetchall()


def listar_tipos_transporte():  # medios según los vehículos cargados; los usa crear regla
    with get_postgres_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT DISTINCT tipo FROM vehiculo ORDER BY tipo")
        return [row[0] for row in cur.fetchall()]


def crear_tipo_carga(codigo, descripcion):  # guarda una categoría; la usa registrar_tipo_carga
    with get_postgres_connection() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO tipo_carga (codigo, descripcion) VALUES (%s, %s)",
                    (codigo, descripcion))


def agregar_carga(id_envio, tipo_carga, peso_kg, fragil, descripcion=None):  # guarda una partida de carga; la usa registrar_partida_carga
    with get_postgres_connection() as conn, conn.cursor() as cur:
        cur.execute("""INSERT INTO envio_carga
                       (id_envio, tipo_carga, peso_kg, fragil, descripcion)
                       VALUES (%s, %s, %s, %s, %s) RETURNING id_envio_carga""",
                    (id_envio, tipo_carga, peso_kg, fragil, descripcion))
        return cur.fetchone()[0]


def listar_cargas_envio(id_envio):  # partidas de un envío; la usa la verificación de los datos de ejemplo
    with get_postgres_connection() as conn, conn.cursor() as cur:
        cur.execute("""SELECT ec.id_envio_carga, ec.tipo_carga, tc.descripcion,
                              ec.peso_kg, ec.fragil, ec.descripcion
                       FROM envio_carga ec JOIN tipo_carga tc ON tc.codigo = ec.tipo_carga
                       WHERE ec.id_envio = %s ORDER BY ec.id_envio_carga""", (id_envio,))
        return cur.fetchall()


def actualizar_distancia_tramo(id_tramo, distancia_km):  # guarda los km de un tramo; la usa registrar_distancia_tramo
    with get_postgres_connection() as conn, conn.cursor() as cur:
        cur.execute("UPDATE tramo SET distancia_km = %s WHERE id_tramo = %s",
                    (distancia_km, id_tramo))
        return cur.rowcount == 1  # False si el tramo no existe


def listar_reglas():  # todas las versiones de reglas; la usa la opción 5 del menú de tarifas
    with get_postgres_connection() as conn, conn.cursor() as cur:
        cur.execute("""SELECT id_regla, codigo, version, moneda, vigente_desde,
                              vigente_hasta, estado
                       FROM regla_tarifaria_version ORDER BY codigo, version DESC""")
        return cur.fetchall()


def crear_regla(codigo, version, moneda, vigente_desde, vigente_hasta,  # guarda la versión en BORRADOR con sus componentes; la usa crear_regla del servicio
                creada_por, componentes):
    with get_postgres_connection() as conn, conn.cursor() as cur:
        cur.execute("""INSERT INTO regla_tarifaria_version
                       (codigo, version, moneda, vigente_desde, vigente_hasta, creada_por)
                       VALUES (%s, %s, %s, %s, %s, %s) RETURNING id_regla""",
                    (codigo, version, moneda, vigente_desde, vigente_hasta, creada_por))
        id_regla = cur.fetchone()[0]
        for component in componentes:  # un INSERT por componente, en la misma transacción
            cur.execute("""INSERT INTO regla_tarifaria_componente
                           (id_regla, criterio, selector, ambito, base_calculo, importe)
                           VALUES (%s, %s, %s, %s, %s, %s)""",
                        (id_regla, component["criterio"], component.get("selector"),
                         component["ambito"], component["base_calculo"], component["importe"]))
        return id_regla


def obtener_regla(id_regla):  # una regla con sus componentes; la usan aprobar regla y el listado
    with get_postgres_connection() as conn, conn.cursor() as cur:
        cur.execute("""SELECT id_regla, codigo, version, moneda, vigente_desde,
                              vigente_hasta, estado
                       FROM regla_tarifaria_version WHERE id_regla = %s""", (id_regla,))
        row = cur.fetchone()
        if row is None:
            return None
        cur.execute("""SELECT id_componente, criterio, selector, ambito,
                              base_calculo, importe
                       FROM regla_tarifaria_componente WHERE id_regla = %s
                       ORDER BY id_componente""", (id_regla,))
        return {
            "id_regla": row[0], "codigo": row[1], "version": row[2],
            "moneda": row[3], "vigente_desde": row[4], "vigente_hasta": row[5],
            "estado": row[6],
            "componentes": [dict(zip(
                ("id_componente", "criterio", "selector", "ambito", "base_calculo", "importe"), x
            )) for x in cur.fetchall()],
        }


def aprobar_regla(id_regla, usuario_id, referencia):  # aprueba un BORRADOR y reemplaza la versión anterior; la usa aprobar_regla del servicio
    with get_postgres_connection() as conn, conn.cursor() as cur:
        cur.execute("""SELECT codigo, estado FROM regla_tarifaria_version
                       WHERE id_regla = %s FOR UPDATE""", (id_regla,))
        row = cur.fetchone()
        if row is None or row[1] != "BORRADOR":  # la regla quedó bloqueada (FOR UPDATE); solo se aprueba un BORRADOR
            raise ValueError("La regla no existe o ya no está en borrador.")
        cur.execute("""SELECT COUNT(*) FROM regla_tarifaria_componente
                       WHERE id_regla = %s AND criterio = 'BASE'
                         AND ambito = 'ENVIO' AND base_calculo = 'FIJO'
                         AND selector IS NULL""", (id_regla,))
        if cur.fetchone()[0] != 1:  # tiene que tener exactamente un cargo base
            raise ValueError("La regla debe tener exactamente un componente base fijo por envío.")
        cur.execute("""SELECT id_regla FROM regla_tarifaria_version
                       WHERE codigo = %s AND estado = 'APROBADA' FOR UPDATE""", (row[0],))
        previous = cur.fetchone()  # la aprobada actual del mismo código, también bloqueada
        if previous:  # pasa a REEMPLAZADA, con auditoría
            cur.execute("""INSERT INTO regla_tarifaria_auditoria
                           (id_regla, estado_anterior, estado_nuevo, motivo,
                            usuario_id, id_transaccion)
                           VALUES (%s, 'APROBADA', 'REEMPLAZADA', %s, %s, txid_current())""",
                        (previous[0], f"Reemplazada por versión {id_regla}", usuario_id))
            cur.execute("""UPDATE regla_tarifaria_version SET estado = 'REEMPLAZADA'
                           WHERE id_regla = %s""", (previous[0],))
        cur.execute("""INSERT INTO regla_tarifaria_auditoria
                       (id_regla, estado_anterior, estado_nuevo, motivo,
                        usuario_id, id_transaccion)
                       VALUES (%s, 'BORRADOR', 'APROBADA', %s, %s, txid_current())""",
                    (id_regla, referencia, usuario_id))
        cur.execute("""UPDATE regla_tarifaria_version
                       SET estado = 'APROBADA', referencia_aprobacion = %s,  -- la nueva pasa a APROBADA
                           aprobado_por = %s, aprobado_en = CURRENT_TIMESTAMP
                       WHERE id_regla = %s""", (referencia, usuario_id, id_regla))


