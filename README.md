
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

## Procesos periódicos de sensores y predicciones

Los procesos se ejecutan una vez por invocación. En Windows se pueden
programar con el Programador de tareas; no requieren mantener la aplicación
abierta ni instalar un scheduler de Python.

El lanzador admite estos trabajos:

- `sensores`: revisa sensores activos cada vez que se invoca. El umbral
  predeterminado es de 24 horas sin lecturas. La clave de deduplicación de
  alertas usa el día calendario de `America/Argentina/Buenos_Aires`.
- `predicciones`: actualiza las predicciones de envíos activos. La fecha diaria
  se determina en `America/Argentina/Buenos_Aires` y se conserva una predicción
  por envío y día, actualizando el registro de ese día si se vuelve a ejecutar.
- `todos`: ejecuta predicciones y luego la revisión de sensores. Se conserva
  como opción manual general; para las tareas programadas se recomienda elegir
  el trabajo específico.

Ejemplos de ejecución manual desde la raíz del proyecto:

```powershell
.\.venv\Scripts\python.exe .\ejecutar_procesos.py --job sensores --horas-sensores 24
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
| Revisión de sensores | Repetir cada 1 hora | `<raíz>\.venv\Scripts\python.exe` | `<raíz>\ejecutar_procesos.py --job sensores --horas-sensores 24` |
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

### Estado de facturación automática y cierre mensual

`revisar_envios_potencialmente_facturables()` conserva una vista preliminar de
solo lectura basada en el estado PostgreSQL. `procesar_facturacion_automatica()`
usa evidencia de entrega y validaciones financieras, pero permanece deshabilitado
y fuera del lanzador mientras no exista el flujo de carga y aprobación de
tarifas, moneda y configuración fiscal.

La migración `scripts/migrations/002_cierres_cuenta_corriente.sql` prepara una
tabla de cierres con unicidad por cliente y período y una referencia al saldo
inicial utilizado. No la apliques hasta revisar y autorizar el esquema. La
`cerrar_cuenta_mensual()` prepara un snapshot solo cuando existe una apertura
aprobada, moneda explícita, documentos conciliados con el ledger y el saldo
acumulado coincide. El servicio no modifica el saldo de la cuenta y no está
integrado al lanzador. Los flujos manuales actuales de factura y pago todavía
no escriben ledger, por lo que sus documentos bloquean el cierre hasta
conciliarlos. Ajustes, reversos de pagos y anulaciones sin crédito íntegro quedan
bloqueados: el esquema actual no registra aprobación de ajustes ni un flujo de
reverso. Las migraciones `003` y `004` deben estar aplicadas antes de invocar el
servicio, porque utiliza el ledger, las aperturas y las correcciones. Para
proteger los snapshots contra cambios directos, preparar y revisar también
`006_cierres_inmutables.sql` después de crear la tabla; el servicio y la tabla
única ya evitan reemplazar cierres por reejecución. Ninguna migración fue
aplicada por la aplicación y su estado en cada instalación debe verificarse por
separado.

Las migraciones `003_cierres_y_movimientos_financieros.sql`,
`004_tarifas_facturacion_auditable.sql` y
`005_facturacion_periodica_auditoria.sql` preparan extensiones aditivas para
aperturas aprobadas, movimientos, cierres, perfiles fiscales, tarifas por envío,
facturas enlazadas a eventos y correcciones auditables. No insertan tarifas,
códigos de moneda ni reglas fiscales. Los archivos del proyecto no permiten
determinar si las migraciones anteriores se aplicaron en alguna instalación;
cada entorno debe revisar su historial antes de decidir el orden de aplicación. Estas
migraciones no están aplicadas por la aplicación.

Las validaciones financieras de `app.utils.validaciones_financieras` son puras
y no acceden a bases de datos. Bloquean tarifas incompletas, moneda no
configurada, desacuerdos entre evento y estado, facturas originales duplicadas,
aperturas sin respaldo y diferencias de conciliación sin aprobación. Todavía
no existe una pantalla ni una operación de la aplicación para cargar y aprobar
tarifas, moneda y configuración fiscal. Por eso
`procesar_facturacion_automatica()` permanece deshabilitado en el código hasta
que exista y se valide ese flujo y se apliquen las migraciones requeridas.

El proceso compara los eventos `ENTREGADO` de MongoDB con el estado de
PostgreSQL y bloquea eventos duplicados, sincronizaciones pendientes o estados
discordantes. Los bloqueos y errores se registran en
`auditoria_facturacion_periodica` cuando la estructura está disponible; los
fallos de auditoría también se registran en `logs/app.log`. Las facturas
manuales históricas no identifican al envío, por lo que la emisión automática
se bloquea para clientes con facturas sin vínculo hasta que se concilien.

La frecuencia propuesta es facturación diaria y cierre mensual. La facturación
no está integrada al lanzador; el cierre mensual tampoco. Ninguna
tarea está configurada en Windows.

## Funcionalidades implementadas

### Clientes — PostgreSQL

- Registrar clientes.
- Listar y buscar clientes.
- Modificar clientes.
- Eliminar clientes.

### Usuarios y roles — PostgreSQL

- Registrar, consultar, modificar y eliminar usuarios.
- Registrar, consultar, modificar y eliminar roles.
- Asignar clientes y roles a usuarios.
- Gestionar estados de usuarios.
- Almacenar contraseñas mediante hash.
- Definir niveles de permisos.

### Sesiones — PostgreSQL

- Registrar inicios de sesión.
- Registrar cierres de sesión.
- Consultar sesiones activas.

**Pendiente:** aplicar los permisos a los menús mediante una sesión autenticada.

### Envíos — PostgreSQL

- Registrar, listar y buscar envíos.
- Modificar y eliminar envíos.
- Asociar envíos a clientes.
- Gestionar estados y prioridades.
- Validar cambios de origen y destino cuando existen tramos.

### Vehículos y tramos — PostgreSQL

- Registrar, consultar, modificar y eliminar vehículos.
- Registrar tramos de transporte.
- Consultar tramos de un envío.
- Validar medios de transporte y fechas.

### Contenedores — PostgreSQL

- Registrar, consultar, modificar y eliminar contenedores.
- Validar códigos internacionales ISO 6346.
- Asociar contenedores a envíos.
- Consultar y desasociar contenedores.

### Sensores IoT — PostgreSQL

- Registrar sensores.
- Consultar sensores por ID.
- Listar sensores.
- Consultar sensores de un contenedor.
- Modificar y eliminar sensores.
- Validar tipo, estado y fecha de instalación.

## Funcionalidades pendientes

### Cassandra

- Registrar lecturas IoT.
- Consultar historial por sensor.
- Consultar lecturas por contenedor.
- Consultar la última lectura.
- Integrar las lecturas con sensores de PostgreSQL.

### MongoDB

- Registrar eventos logísticos.
- Gestionar alertas.
- Implementar mensajería.
- Almacenar predicciones.

### Neo4j

- Crear nodos y relaciones logísticas.
- Representar rutas.
- Consultar trazabilidad de envíos.
- Sincronizar información con PostgreSQL.

### Otras funcionalidades

- Gestión completa de incidentes.
- Reportes y facturación.
- Análisis y predicciones.
- Control de acceso por permisos.
- Pruebas integrales entre bases de datos.

## Estructura del proyecto

```text
Tp_bdd2/
│
├── app/
│   ├── database/
│   ├── models/
│   ├── repositories/
│   ├── services/
│   ├── ui/
│   └── utils/
│
├── scripts/
│   ├── postgresql_schema.sql
│   ├── mongodb_schema.js
│   ├── cassandra_schema.cql
│   └── neo4j_schema.cypher
│
├── .env.example
├── .gitignore
├── docker-compose.yml
├── main.py
├── requirements.txt
├── test_cliente_repository.py
└── test_conexiones.py
```

## Estado actual

El proyecto está en desarrollo.

La gestión transaccional en PostgreSQL se encuentra implementada en sus módulos principales.

Los esquemas y conexiones de MongoDB, Cassandra y Neo4j están preparados, pero sus funcionalidades operativas todavía deben desarrollarse.

El objetivo es integrar los cuatro motores mediante procesos de persistencia políglota.
