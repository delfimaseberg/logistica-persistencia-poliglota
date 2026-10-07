# Sistema de Gestión Logística - Persistencia Políglota

Trabajo práctico final de **Ingeniería de Datos II**.

El proyecto consiste en una aplicación de consola desarrollada en Python para la gestión de una plataforma logística, utilizando un enfoque de **persistencia políglota**.

## Tecnologías utilizadas

El sistema utiliza cuatro motores de bases de datos:

- **PostgreSQL**: información transaccional y estructurada.
- **MongoDB**: eventos logísticos, alertas, mensajes y predicciones.
- **Cassandra**: almacenamiento de lecturas de sensores IoT.
- **Neo4j**: representación de relaciones y trazabilidad mediante grafos.

La aplicación está desarrollada en **Python**.

### Arquitectura local

- PostgreSQL se ejecuta instalado localmente en Windows.
- MongoDB, Cassandra y Neo4j se ejecutan mediante Docker Desktop.
- La aplicación Python se ejecuta localmente y se conecta a las cuatro bases.

---

# Requisitos

Antes de ejecutar el proyecto es necesario tener instalado:

- Python
- Git
- PostgreSQL
- Docker Desktop

No es necesario instalar MongoDB, Cassandra ni Neo4j individualmente, ya que se ejecutan mediante Docker.

---

# 1. Clonar el repositorio

Desde una terminal:

```bash
git clone https://github.com/delfimaseberg/logistica-persistencia-poliglota.git
```

Entrar a la carpeta:

```bash
cd logistica-persistencia-poliglota
```

---

# 2. Crear el entorno virtual de Python

Crear el entorno virtual:

```bash
python -m venv .venv
```

En Windows PowerShell, activarlo con:

```powershell
.\.venv\Scripts\Activate.ps1
```

Cuando esté activo debería aparecer:

```text
(.venv)
```

al comienzo de la terminal.

---

# 3. Instalar las dependencias

Con el entorno virtual activado:

```bash
pip install -r requirements.txt
```

---

# 4. Configurar las variables de entorno

El repositorio contiene el archivo:

```text
.env.example
```

Cada integrante debe crear su propio archivo:

```text
.env
```

Se puede copiar `.env.example` y renombrar la copia como `.env`.

El archivo debe tener esta estructura:

```env
MONGO_URI=mongodb://localhost:27017
MONGO_DB=logistica_poliglota

NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=TU_PASSWORD

POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=logistica_poliglota
POSTGRES_USER=postgres
POSTGRES_PASSWORD=TU_PASSWORD

CASSANDRA_HOST=127.0.0.1
CASSANDRA_PORT=9042
```

Cada integrante debe colocar sus propias contraseñas.

**IMPORTANTE:** el archivo `.env` contiene credenciales y no debe subirse a GitHub.

---

# 5. Levantar MongoDB, Cassandra y Neo4j

Primero asegurarse de que **Docker Desktop esté abierto y funcionando**.

Desde la raíz del proyecto ejecutar:

```bash
docker compose up -d
```

Para comprobar que los contenedores estén funcionando:

```bash
docker ps
```

Deberían aparecer los contenedores correspondientes a:

- MongoDB
- Cassandra
- Neo4j

---

# 6. Configurar PostgreSQL

PostgreSQL debe estar instalado y ejecutándose localmente.

Ingresar a PostgreSQL:

```bash
psql -U postgres
```

Crear la base:

```sql
CREATE DATABASE logistica_poliglota;
```

Conectarse:

```sql
\c logistica_poliglota
```

Ejecutar el script:

```sql
\i 'scripts/postgresql_schema.sql'
```

Si el comando anterior no encuentra el archivo por la ubicación desde la que se abrió `psql`, se puede ingresar directamente desde PowerShell:

```powershell
psql -U postgres -d logistica_poliglota -f scripts/postgresql_schema.sql
```

---

# 7. Configurar MongoDB

Con el contenedor funcionando:

```bash
docker exec -it tp_mongodb mongosh
```

Dentro de MongoDB ejecutar:

```javascript
load("/scripts/mongodb_schema.js")
```

Si el script no está disponible dentro del contenedor, se puede copiar primero:

```bash
docker cp scripts/mongodb_schema.js tp_mongodb:/mongodb_schema.js
```

y luego:

```bash
docker exec -it tp_mongodb mongosh
```

Dentro de `mongosh`:

```javascript
load("/mongodb_schema.js")
```

---

# 8. Configurar Cassandra

Copiar el script al contenedor:

```bash
docker cp scripts/cassandra_schema.cql tp_cassandra:/cassandra_schema.cql
```

Ejecutarlo:

```bash
docker exec -it tp_cassandra cqlsh -f /cassandra_schema.cql
```

Esto crea el keyspace y las tablas necesarias para las lecturas IoT.

---

# 9. Configurar Neo4j

Neo4j queda disponible en:

```text
http://localhost:7474
```

Ingresar utilizando:

```text
Usuario: neo4j
Contraseña: la definida en NEO4J_PASSWORD
```

Abrir el archivo:

```text
scripts/neo4j_schema.cypher
```

y ejecutar su contenido desde Neo4j Browser para crear las restricciones necesarias.

---

# 10. Probar las conexiones

Con las bases funcionando y el `.env` configurado:

```bash
python test_conexiones.py
```

Si todo está correctamente configurado deberían funcionar las conexiones a:

- PostgreSQL
- MongoDB
- Cassandra
- Neo4j

---

# 11. Ejecutar la aplicación

Desde la raíz del proyecto:

```bash
python main.py
```

Se mostrará el menú principal:

```text
==========================================
   SISTEMA DE GESTIÓN LOGÍSTICA
==========================================
1. Gestión de clientes
2. Gestión de usuarios
3. Gestión de envíos
4. Gestión de contenedores y sensores
5. Monitoreo IoT
6. Trazabilidad de envíos
7. Gestión de incidentes y alertas
8. Mensajería
9. Reportes y facturación
10. Análisis y predicciones
0. Salir
```

---

# Funcionalidades implementadas actualmente

Actualmente se encuentran implementadas y conectadas a PostgreSQL:

### Gestión de clientes

- Registrar cliente
- Listar clientes
- Buscar cliente
- Modificar cliente
- Eliminar cliente

### Gestión de usuarios

- Registrar usuario
- Listar usuarios
- Buscar usuario
- Modificar usuario
- Eliminar usuario
- Selección de cliente
- Selección de rol
- Estado ACTIVO / INACTIVO
- Almacenamiento de contraseña mediante hash

### Gestión de roles

- Registrar rol
- Listar roles
- Buscar rol
- Modificar rol
- Eliminar rol
- Niveles de permisos

El resto de los módulos se encuentra en desarrollo.

---

# Estructura principal

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

## Estado del proyecto

El proyecto se encuentra actualmente en desarrollo. La estructura de persistencia políglota y las conexiones con los cuatro motores de bases de datos ya están configuradas.