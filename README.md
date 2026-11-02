
# Sistema de Gestión Logística - Persistencia Políglota

Trabajo práctico final de **Ingeniería de Datos II**.

Aplicación de consola desarrollada en Python para gestionar operaciones logísticas utilizando cuatro motores de bases de datos.

## Tecnologías utilizadas

- **PostgreSQL:** datos transaccionales y estructurados.
- **MongoDB:** eventos logísticos, alertas, mensajes y predicciones.
- **Cassandra:** lecturas de sensores IoT.
- **Neo4j:** relaciones y trazabilidad mediante grafos.
- **Python:** lógica de negocio e interfaz de consola.

### Arquitectura local

- PostgreSQL instalado en Windows.
- MongoDB, Cassandra y Neo4j ejecutados mediante Docker Desktop.
- Aplicación Python ejecutada localmente.

## Requisitos

- Python
- Git
- PostgreSQL
- Docker Desktop

## Instalación

### 1. Clonar el repositorio

```bash
git clone https://github.com/delfimaseberg/logistica-persistencia-poliglota.git
cd logistica-persistencia-poliglota
```

### 2. Crear el entorno virtual

```bash
python -m venv .venv
```

Activarlo en Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

### 3. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 4. Configurar variables de entorno

Copiar `.env.example` como `.env` y completar las credenciales locales.

Variables necesarias:

```env
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=logistica_poliglota
POSTGRES_USER=postgres
POSTGRES_PASSWORD=TU_PASSWORD

MONGO_URI=mongodb://localhost:27017
MONGO_DB=logistica_poliglota

CASSANDRA_HOST=127.0.0.1
CASSANDRA_PORT=9042

NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=TU_PASSWORD
```

**Importante:** nunca subir `.env` ni contraseñas reales a GitHub.

### 5. Levantar los contenedores

Con Docker Desktop abierto:

```bash
docker compose up -d
docker ps
```

### 6. Configurar las bases de datos

Los scripts se encuentran en `scripts/`:

- `postgresql_schema.sql`
- `mongodb_schema.js`
- `cassandra_schema.cql`
- `neo4j_schema.cypher`

Cada script debe ejecutarse en su motor correspondiente.

### 7. Probar conexiones

```bash
python test_conexiones.py
```

Este script comprueba las conexiones a PostgreSQL, MongoDB, Cassandra y Neo4j.

### 8. Ejecutar la aplicación

```bash
python main.py
```

## Menús de la aplicación

Después de iniciar sesión, el menú depende de a quién pertenece el usuario
(su "parte"), no solo de su nivel de permisos:

- **Usuarios internos** (sin cliente, proveedor ni operador): menú de gestión.
  Dentro de él, cada opción exige además un nivel mínimo.
- **Usuarios de un cliente**: portal del cliente. Solo consultan lo suyo; no
  emiten, no cobran ni cierran nada, aunque tengan nivel 5.
- **Usuarios de un operador logístico o de un proveedor**: portal propio.

Las funciones internas están protegidas también en el código: cada servicio
verifica el permiso por sí mismo (`@requiere_permiso` en
`app/services/autenticacion.py`), así que un usuario de cliente, operador o
proveedor, o uno de nivel menor, no puede ejecutarlas aunque llegue a ellas
(ver "Seguridad y validaciones").

### Menú interno

| Opción | Menú | Nivel |
|---|---|---|
| 1 | Gestión de clientes | 1 |
| 2 | Gestión de usuarios (roles; sesiones activas y usuarios bloqueados; restablecer contraseña y desbloquear: nivel 5) | 3 |
| 3 | Gestión de envíos (vehículos, tramos, contenedores del envío) | 1 |
| 4 | Gestión de contenedores y sensores | 1 |
| 5 | Monitoreo IoT (incluye "Simular falla de sensor") | 1 |
| 6 | Trazabilidad de envíos (eventos, seguimiento, ruta, recorrido, operadores y red en Neo4j) | 1 |
| 7 | Gestión de incidentes y alertas (detección de anomalías y fallas de sensor; reglas de alerta) | 1 |
| 8 | Mensajería | 1 |
| 9 | Facturación y cobranzas | 1 (operaciones: 3) |
| 10 | Reportes | 1 |
| 11 | Análisis y predicciones (incluye alertas climáticas) | 1 |
| 12 | Proveedores (ABM y cuenta corriente) | 3 |
| 13 | Operadores logísticos (ABM, tramos y cuenta corriente) | 3 |
| 14 | Cambiar mi contraseña | — |
| 15 | Cerrar sesión | — |
| 0 | Salir | — |

**Facturación y cobranzas:** cotizar un envío; emitir la factura de un envío
entregado; facturación automática hasta una fecha de corte; consultar facturas
y su detalle; registrar pagos; cuenta corriente de un cliente; estado de
facturación de los envíos entregados (cliente y operadores); precios de
transporte (tarifa estándar); apertura de cuenta corriente; cierre mensual;
reglas tarifarias y datos de carga (avanzado).

**Reportes** (filtros por período y, donde aplica, por cliente; exportables a CSV):

| Submenú | Reportes | Bases |
|---|---|---|
| Operativos | Envíos por país de destino (con países de origen), por estado, por cliente; envíos demorados; incidentes abiertos | PostgreSQL; demorados también MongoDB (eventos RETRASO) |
| Analíticos | Tiempos máximos y mínimos por cliente; promedio de incidentes por país / estado / cliente; tiempos promedio de entrega; costos por tipo de transporte (cobrado vs costo de operadores) | PostgreSQL + MongoDB (tiempo de tránsito) |
| Rankings y desempeño | Rutas con más incidentes; clientes por volumen (contenedores, toneladas, kg); desempeño a tiempo vs tarde por ruta, operador y mes | PostgreSQL + Neo4j (operadores) |
| Reportes cobrables | Generar para un cliente, listar, ver | según el tipo |
| Predictivos | Riesgo de demora de los envíos en curso; rutas que suelen atrasarse; alertas climáticas vigentes y envíos afectados | MongoDB (predicciones, alertas climáticas, eventos RETRASO) + PostgreSQL |

Luego: 6. Facturación por cliente · 7. Ingresos mensuales (cobros).

Definiciones (sin tolerancia): **a tiempo** = entrega ≤ mayor llegada estimada de
los tramos; **tarde** = después; **demorado** = no entregado ni cancelado con la
llegada estimada vencida. Los envíos anteriores a la migración 014 no tienen
países y figuran como "Sin dato".

**Reportes cobrables** (los pide el cliente desde su portal o un usuario interno
para un cliente; siempre sobre los datos de ESE cliente). Ciclo: SOLICITADO →
GENERADO (archivo CSV o PDF en `reportes_generados/`; el hash SHA-256 queda en la base) →
FACTURADO (una factura por reporte, con su movimiento en la cuenta corriente).
Si la generación falla queda ERROR y no se factura.

| Tipo | Contenido | Bases | Precio + IVA |
|---|---|---|---|
| INCIDENTES | Incidentes de sus envíos y alertas de sus contenedores | PostgreSQL + MongoDB | $15.000 |
| PUNTUALIDAD | Envíos a tiempo, tarde y demorados, con retrasos informados | PostgreSQL + MongoDB | $12.000 |
| OPERADORES | Operadores que llevaron sus contenedores, por tramo | Neo4j + PostgreSQL | $10.000 |
| CONDICIONES_CARGA | Temperatura, humedad, lecturas fuera de rango (según las reglas de alerta) y GPS por contenedor | Cassandra + PostgreSQL | $25.000 |
| PREDICTIVO | Riesgo de demora de sus envíos en curso, al día de la solicitud (sin período) | MongoDB + PostgreSQL | $15.000 |

Los precios se cambian en Facturación y cobranzas → "Precios de reportes
cobrables"; rigen para los reportes que se piden después.

### Portal del cliente

1. Mis envíos
2. Seguimiento de un envío (línea de tiempo)
3. Eventos de un envío
4. Ruta y operadores de un envío
5. ¿Quién llevó mi contenedor?
6. Mis facturas
7. Detalle de una factura
8. Mi cuenta corriente
9. Mis reportes (listar, solicitar un reporte cobrable, ver uno)
10. Mensajería
11. Cambiar mi contraseña
12. Cerrar sesión / 0. Salir

El cliente se toma de la sesión; si se pide un envío o una factura de otro
cliente, la respuesta es "no existe".

### Portal del operador logístico y del proveedor

- Operador: 1. Mensajería · 2. Mis tramos realizados · 3. Mis facturas y lo
  que nos falta pagarles · 4. Cambiar mi contraseña · 5. Cerrar sesión · 0. Salir.
- Proveedor: 1. Mensajería · 2. Mis facturas y lo que nos falta pagarles ·
  3. Cambiar mi contraseña · 4. Cerrar sesión · 0. Salir.

### Alertas, fallas de sensor y mensajes

- **Reglas de alerta** (Incidentes → 7, tabla `regla_alerta`): umbrales de
  temperatura (mín./máx.), humedad, vibración, batería, horas sin transmisión,
  salto brusco de temperatura y cantidad de lecturas idénticas. Se pueden tener
  varios niveles por variable (por ejemplo, > 8 °C Alta y > 12 °C Crítica): se
  informa el más severo que se cumple. Valores validados por rango físico.
- **Fallas del sensor** (un sensor que mide mal): valor imposible (fuera del
  rango físico o no numérico), lecturas congeladas (las últimas N idénticas) y
  salto brusco (más de X °C entre lecturas a menos de 60 min). Generan alerta y
  mensaje, pero no incidente; una lectura con valor imposible no se evalúa
  contra los umbrales de la carga.
- **Mensaje por alerta:** toda alerta nueva deja un mensaje "Alerta" (remitente
  "Sistema de alertas") a los usuarios internos activos y a los usuarios del
  cliente del envío. Un índice único (alerta, destinatario) evita repetidos.
- **Sensores al entregar:** al registrar el evento ENTREGADO, los sensores de
  sus contenedores pasan a Inactivo (motivo "Entrega del envío N"); si el
  contenedor vuelve a asociarse a un envío, se reactivan.

### Predicción de riesgo (entidad Predicción de Riesgo)

Cada día, por envío en curso: riesgo climático, riesgo operativo, probabilidad
de demora y fecha de cálculo (colección `predicciones_riesgo`). La probabilidad
combina como eventos independientes, `1 − Π(1 − p)`:

| Factor | p |
|---|---|
| Historial de la ruta (entregados tarde o con RETRASO) | tasa de la ruta; con menos de 2 entregados, la tasa general |
| Alerta climática que lo afecta (ciudad de un tramo durante el tramo, o país/ciudad del envío durante el viaje) | Baja 0,10 · Media 0,25 · Alta 0,45 · Extrema 0,70 |
| Cada incidente abierto | Crítica 0,40 · Alta 0,30 · Media 0,20 · otra 0,10 |
| Llegada estimada vencida | 1 (demora confirmada) |

Nivel: ALTO desde 60 %, MEDIO desde 30 %; el nivel final es el mayor entre este
y el del puntaje de plazo e incidentes. Sin fechas estimadas queda
"Información insuficiente" salvo que la probabilidad ya dé ALTO. Las alertas
climáticas se registran a mano (Análisis y predicciones → 7), sin API externa.

### Mensajería: a quién se puede escribir

| Usuario | Puede escribir a |
|---|---|
| Interno | Todos los usuarios activos |
| Cliente | Usuarios internos, usuarios de su mismo cliente y usuarios de los operadores que realizaron tramos de sus envíos |
| Operador | Usuarios internos y usuarios de los clientes cuyos envíos transportó |
| Proveedor | Usuarios internos |

La regla se aplica al listar destinatarios y otra vez al enviar. Los usuarios
externos no ven el email de los demás y no crean grupos ni agregan miembros
(participan en los grupos donde los suma un usuario interno).

## Procesos periódicos de sensores y predicciones

Los procesos se ejecutan una vez por invocación. En Windows se pueden
programar con el Programador de tareas; no requieren mantener la aplicación
abierta ni instalar un scheduler de Python.

El lanzador admite estos trabajos:

- `sensores`: revisa sensores activos cada vez que se invoca: sin transmisión
  (umbral de la regla de alerta activa; `--horas-sensores` lo reemplaza), y las
  lecturas recientes (umbrales de la carga y fallas del sensor), con los
  mensajes de cada alerta nueva. La clave de deduplicación de las alertas de
  sin transmisión usa el día calendario de `America/Argentina/Buenos_Aires`.
- `predicciones`: actualiza las predicciones de envíos activos (clima,
  historial de rutas y probabilidad de demora). La fecha diaria
  se determina en `America/Argentina/Buenos_Aires` y se conserva una predicción
  por envío y día, actualizando el registro de ese día si se vuelve a ejecutar.
- `todos`: ejecuta predicciones y luego la revisión de sensores. Se conserva
  como opción manual general; para las tareas programadas se recomienda elegir
  el trabajo específico.

Ejemplos de ejecución manual desde la raíz del proyecto:

```powershell
.\.venv\Scripts\python.exe .\ejecutar_procesos.py --job sensores
.\.venv\Scripts\python.exe .\ejecutar_procesos.py --job predicciones
```

Estas invocaciones realizan las operaciones normales del sistema: leen
PostgreSQL y Cassandra y pueden escribir alertas o predicciones en MongoDB.
No son comandos de prueba; para probar lógica se deben usar las pruebas
unitarias con mocks.

### Programador de tareas de Windows

Crear dos tareas independientes. En ambas, configurar **Iniciar en** con la
ruta absoluta de la raíz del proyecto y **Si la tarea ya se está ejecutando**
con **No iniciar una instancia nueva**.

| Tarea | Desencadenador | Programa | Argumentos |
|---|---|---|---|
| Revisión de sensores | Repetir cada 1 hora | `<raíz>\.venv\Scripts\python.exe` | `<raíz>\ejecutar_procesos.py --job sensores` |
| Predicciones diarias | Todos los días a las 09:00, hora de Argentina | `<raíz>\.venv\Scripts\python.exe` | `<raíz>\ejecutar_procesos.py --job predicciones` |

Reemplazar `<raíz>` por la ruta absoluta del workspace. La acción debe usar la
ruta de Python de `.venv`, no el alias global `python`. Confirmar que Windows
esté configurado con la zona horaria de Argentina para que el horario diario
coincida con las 09:00 indicadas.

Los errores generales y por sensor/envío se registran en `logs/app.log`. El
lanzador devuelve código de salida `1` si falla un proceso o algún elemento, y
`0` si finaliza sin errores; esto permite que el Programador de tareas refleje
fallos parciales.

Antes de ejecutar cualquier versión nueva que guarde predicciones —desde el
menú de la aplicación, el lanzador o el Programador de tareas— revisar y aplicar
la migración `scripts/migrations/001_predicciones_unicas_por_dia.js` contra la
base prevista. Detener las ejecuciones de predicciones y hacer una copia de
seguridad antes de aplicarla. La migración comprueba primero documentos
inválidos y duplicados por envío y día argentino; si encuentra duplicados,
aborta antes de actualizar documentos o crear índices. Resolverlos y volver a
revisar la migración antes de activar la versión nueva.

Para la configuración local predeterminada, desde la raíz del proyecto:

```powershell
mongosh "mongodb://localhost:27017/logistica_poliglota" --file .\scripts\migrations\001_predicciones_unicas_por_dia.js
```

Si `MONGO_URI` apunta a otro servidor, sustituir la URI del comando por la de
la base prevista; no aplicar la migración a una base de uso cotidiano por error.

### Facturación, cobros y cuentas corrientes

- **Una factura por envío**, cuando el envío está Entregado (la fecha real de
  entrega la fija el evento ENTREGADO). Se emite a mano (Facturación → 2) o con
  la facturación automática (Facturación → 3, o `ejecutar_procesos.py --job
  facturacion`), que es idempotente: no repite envíos ya facturados.
- **Tarifa estándar** (Facturación → 9): cargo base por envío más un precio por
  tramo según el medio de transporte; IVA 21 %; moneda ARS. Cada cambio de
  precios es una versión nueva; las facturas guardan la versión que usaron.
- **Reportes cobrables**: una factura por reporte, al generarse.
- **Cuenta corriente** de cada cliente: libro de movimientos (factura +, pago −).
  El saldo siempre coincide con la apertura más los movimientos.
- **Apertura** (Facturación → 10) y **cierre mensual** (Facturación → 11, o
  `ejecutar_procesos.py --job cierre --periodo AAAA-MM`): el cierre guarda un
  resumen inmutable por cliente y no se puede cerrar un mes que no terminó.
- **Proveedores y operadores**: facturas recibidas (las de operadores, por tramo
  de un envío entregado), pagos emitidos, saldo de lo que se les debe y
  facturas vencidas o por vencer (30 días por defecto).

### Reglas tarifarias (avanzado)

Facturación → 14 permite registrar categorías de carga, partidas (peso real y
fragilidad) y distancias documentadas de tramos, y crear y aprobar reglas
versionadas. Las facturas usan la tarifa estándar; estas reglas quedan como
registro auditable de la configuración comercial.

## Seguridad y validaciones

### Contraseñas

Se aplican al **crear, cambiar o restablecer** una contraseña. Las contraseñas
ya guardadas no se revalidan: los usuarios existentes siguen entrando con la suya.

| Regla | Valor |
|---|---|
| Largo | 8 a 128 caracteres |
| Obligatorio | al menos una mayúscula, una minúscula, un número y un símbolo (cualquier carácter que no sea letra ni número) |
| No se admite | espacios; contener el email (la parte antes de la @, o sus partes separadas por punto, guion o +), el nombre o el apellido, sin distinguir mayúsculas ni tildes, aunque tenga símbolos intercalados. Solo cuentan las partes de 3 letras o más |
| Al cambiarla | tiene que ser distinta de la actual |

- Se escriben siempre ocultas (`getpass`) y se piden **dos veces**. Enter cancela.
- Se guardan solo como hash PBKDF2-SHA256 con sal propia (600.000 iteraciones).
- **Cambiar mi contraseña** (menú interno, opción 14, y en cada portal; siempre justo
  antes de "Cerrar sesión"): pide la contraseña actual. Al cambiarla se cierran las otras sesiones
  abiertas del usuario. Una contraseña actual incorrecta cuenta como intento fallido.
- **Restablecer contraseña de un usuario** (Gestión de usuarios → 8, nivel 5):
  el administrador asigna una contraseña temporal. El usuario la tiene que cambiar
  en su próximo inicio de sesión: si no la cambia, la sesión se cierra. Además se
  cierran las sesiones abiertas del usuario y se quita el bloqueo.
- **Desbloquear usuario** (Gestión de usuarios → 9, nivel 5): limpia los intentos
  fallidos y el bloqueo **sin cambiar la contraseña**.
- Ninguna de estas opciones se aplica a la propia cuenta del administrador: para
  eso está "Cambiar mi contraseña".
- "Modificar usuario" ya no toca la contraseña.

### Bloqueo e inactividad

| Regla | Valor |
|---|---|
| Intentos fallidos seguidos para bloquear | 5 |
| Duración del bloqueo | 15 minutos (se reinicia la cuenta al entrar bien o al vencer el bloqueo) |
| Cierre de sesión por inactividad | 30 minutos sin usar el sistema (la sesión queda en estado EXPIRADA) |

- Mientras está bloqueado: "Demasiados intentos fallidos. Probá de nuevo en N minutos."
- "El usuario está inactivo" se informa solo después de la contraseña correcta,
  para no revelar qué emails existen.
- "Sesiones activas y usuarios bloqueados" (Gestión de usuarios → 7) muestra los
  usuarios bloqueados y hasta cuándo, y cierra las sesiones vencidas por inactividad.
  "Listar usuarios" y "Buscar usuario" muestran el bloqueo y si el usuario tiene
  que cambiar la contraseña.
- Log (`logs/app.log`): solo el id del usuario y lo que pasó (por ejemplo
  `Inicio de sesión fallido: usuario 5 (intento 3 de 5)`, `Usuario 5 bloqueado por
  15 minutos`). **Nunca** la contraseña, su hash ni el email tipeado. Si el email
  no existe, se registra "email no registrado".

### Validaciones de datos

Se aplican al pedir cada dato y otra vez en la capa de datos, antes de escribir
(sirven para cualquier pantalla o proceso). Los largos son los de las columnas.

| Dato | Regla |
|---|---|
| CUIT de clientes | Argentina: 11 dígitos con dígito verificador (algoritmo de AFIP), se guarda como XX-XXXXXXXX-X. Otros países: identificación fiscal de 6 a 13 caracteres (números, puntos, guiones o K) con al menos 5 dígitos |
| CUIT de proveedores y operadores | siempre CUIT argentino con dígito verificador |
| Email | formato válido, hasta 150 caracteres, **único** sin distinguir mayúsculas (usuarios, clientes, proveedores y operadores; también con un índice en la base) |
| Teléfono | opcional; hasta 30 caracteres, al menos 6 dígitos; se admiten +, espacios, guiones y paréntesis |
| Textos | razón social 150, dirección 255, país 80, nombre y apellido 80, origen y destino 150, descripción de rol 255, descripción de incidente y de partida 1000, mensaje 2000, nombre de grupo 100, categoría de carga 40/150 |
| Importes (pagos, facturas recibidas, pagos emitidos, precios de transporte y de reportes, componentes de reglas) | mayores a cero, hasta 2 decimales, máximo **$100.000.000,00 por operación** |
| Saldo inicial de una apertura | puede ser cero; en valor absoluto hasta $100.000.000,00 |
| Cantidades | capacidad de contenedor hasta 100 t; peso de una partida hasta 100.000 kg; distancia de un tramo hasta 40.000 km |
| Fechas | desde ≤ hasta (los reportes vuelven a pedir el período); llegada estimada ≥ salida; vencimiento ≥ emisión; fecha de instalación y de emisión no futuras |

### Permisos y consultas

- Cada servicio que llaman los menús internos verifica el permiso por sí mismo
  (`@requiere_permiso(nivel)` en `app/services/autenticacion.py`), con el mismo
  nivel que su menú, además del control del menú. Los pocos servicios compartidos
  con el portal del cliente solo lo dejan pasar con un dato ya verificado como suyo.
  Un test recorre los menús y falla si algún servicio queda sin control.
- Las consultas SQL reciben los valores siempre como parámetros. Lo único que se
  interpola son nombres de tablas o columnas elegidos de listas fijas del código.
  Un test lo controla.

## Migraciones

Se aplican en orden, una sola vez y con respaldo previo. Todas son idempotentes.

```powershell
psql -U postgres -d logistica_poliglota -v ON_ERROR_STOP=1 -f scripts\migrations\002_cierres_cuenta_corriente.sql
# ... 003 a 015 en orden numérico ...
mongosh "mongodb://localhost:27017/logistica_poliglota" --file scripts\migrations\001_predicciones_unicas_por_dia.js
python scripts\migrations\015_atender_alertas_entregados.py --aplicar
```

| Migración | Contenido |
|---|---|
| 001 (MongoDB) | Una predicción por envío y día (índice único) |
| 002–009 | Cierres, libro de movimientos, tarifas, auditoría, moneda ARS |
| 010–012 | Proveedores, operadores, cuentas corrientes de terceros, usuarios por parte |
| 013 | Factura por envío y por reporte, detalle de factura, fecha real de entrega |
| 014 | Reportes cobrables y países de origen y destino del envío |
| 015 | Reglas de alerta, reporte predictivo, sensores al entregar, cierre de sesiones ajenas |
| 016 | Seguridad: bloqueo por intentos, cambio obligatorio de contraseña, inactividad de sesiones, email único sin distinguir mayúsculas, fechas coherentes en tramos y facturas recibidas, CUIT corregido de Distribuidora del Sur |

## Datos de ejemplo y verificación

```powershell
$env:DEMO_PASSWORD = "<contraseña de los usuarios de ejemplo>"
python scripts\datos_demo\cargar_datos_demo.py --base logistica_poliglota
python scripts\datos_demo\cargar_datos_demo.py --base logistica_poliglota --dia3
python scripts\datos_demo\cargar_datos_demo.py --base logistica_poliglota --dia3b
python scripts\datos_demo\verificar_datos_demo.py
```

`--base` debe coincidir con la base de `.env` (el script no escribe si no
coincide). La verificación recorre los 40 puntos y muestra cuáles dan
resultado. El día de la demo, `--refrescar-lecturas` genera lecturas IoT
recientes, alertas y predicciones.

`scripts\datos_demo\regenerar_hashes_demo.py` pide la contraseña de los usuarios de
ejemplo (oculta), verifica que coincida con el hash guardado y, con `--aplicar`,
genera un hash con sal propia para cada uno (sin cambiar la contraseña). Al final
hace un inicio de sesión real de Delfina, Lucía, Diego, Paula y Sofía.

## Pruebas

```powershell
python -m pytest -q --ignore=tests/integration
```

Las pruebas unitarias no necesitan bases de datos: `tests/conftest.py` bloquea
cualquier conexión real y hace fallar la prueba que la intente. Sus logs van a
una carpeta temporal (no a `logs/app.log`). Las pruebas de integración usan un
entorno Docker aparte (`scripts/run_integration_tests.ps1`, `INTEGRATION_TESTS=1`).

## Estructura del proyecto

```text
Tp_bdd2/
├── app/
│   ├── database/       conexiones a PostgreSQL, MongoDB, Cassandra y Neo4j
│   ├── models/         entidades del dominio
│   ├── repositories/   consultas a cada base
│   ├── services/       reglas de negocio y pantallas
│   ├── ui/             menús
│   └── utils/          validaciones, formato argentino, mensajes de error, exportación
├── scripts/
│   ├── migrations/     001–016
│   ├── datos_demo/     carga de datos de ejemplo y verificación de los 40 puntos
│   └── *_schema.*      esquemas iniciales de las cuatro bases
├── tests/              pruebas unitarias (y de integración en tests/integration)
├── reportes_generados/ archivos de los reportes (no se versiona)
├── logs/               app.log (no se versiona)
├── main.py             aplicación
├── ejecutar_procesos.py procesos periódicos (sensores, predicciones, facturación, cierre)
└── test_conexiones.py  prueba manual de conexión a las cuatro bases
```

## Estado actual

Los 40 puntos del análisis de promoción están implementados y dan resultado
con los datos de ejemplo (`verificar_datos_demo.py`). Cada base cumple su
papel: PostgreSQL para lo transaccional y financiero, MongoDB para eventos,
alertas, mensajes y predicciones, Cassandra para las lecturas IoT y Neo4j para
la red de clientes, envíos, tramos y operadores.
