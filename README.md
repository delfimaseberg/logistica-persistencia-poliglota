
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
