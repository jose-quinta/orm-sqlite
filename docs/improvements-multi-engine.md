# Mejoras Post-Commit: Soporte Multi-Engine

## Basado en los cambios sin commit respecto al tag `7a10a27`

---

## 1. Resumen General

El ORM ha evolucionado de ser exclusivo para SQLite a una arquitectura multi-engine que soporta **SQLite**, **PostgreSQL** y **MySQL**. La pieza central de esta mejora es el **sistema de dialectos**, que abstrae las diferencias sintácticas y de tipos entre motores.

### Archivos involucrados

```
NUEVOS:
  src/orm/db/dialect.py       → Sistema de dialectos (clase base + 3 implementaciones)
  src/orm/db/postgresql.py    → Adaptador PostgreSQL con pool de conexiones
  src/orm/db/mysql.py         → Adaptador MySQL
  src/orm/db/registry.py      → Factory por URL + registry de adaptadores
  requirements.txt            → Dependencias (psycopg2, pymysql)

MODIFICADOS:
  src/orm/db/base.py          → DatabaseAdapter expandido (dialect, savepoints, etc.)
  src/orm/db/sqlite.py        → SQLiteAdapter refactorizado (usa dialecto, sin auto-commit)
  src/orm/db/__init__.py      → Exporta nuevos adaptadores y dialectos
  src/orm/__init__.py          → Exporta las nuevas clases públicas
  src/tests/run_tests.py      → Incluye tests de adaptadores
```

---

## 2. Sistema de Dialectos — `src/orm/db/dialect.py`

### 2.1 Clase Base `Dialect` (ABC)

Define la interfaz que cada motor debe implementar. Sus métodos abstractos son:

| Método | Propósito |
|---|---|
| `name` | Identificador único del motor (`"sqlite"`, `"postgresql"`, `"mysql"`) |
| `param_style` | Estilo de placeholder (`"?"`, `"%s"`) |
| `quote_identifier(name)` | Cómo escapar nombres de tablas/columnas |
| `compile_limit_offset(limit, offset)` | Sintaxis de LIMIT/OFFSET |
| `auto_increment_sql()` | Palabra clave para auto-incremento |
| `type_map` | Mapeo de tipos genéricos a tipos del motor |
| `compile_insert_returning(table, cols)` | `INSERT ... RETURNING` o `None` |
| `compile_upsert(table, cols, conflict_cols)` | UPSERT según el motor |
| `compile_create_index(name, table, cols, unique)` | CREATE INDEX |
| `compile_drop_index(name)` | DROP INDEX |
| `supports_if_not_exists` | Booleano: ¿soporta `IF NOT EXISTS`? |

Métodos concretos (con implementación por defecto):

```python
def placeholders(self, count: int) -> str:
    return ", ".join(self.param_style for _ in range(count))
```

### 2.2 SQLiteDialect

```python
class SQLiteDialect(Dialect):
    name              = "sqlite"
    param_style       = "?"
    quote_identifier  = '"name"'
    auto_increment_sql = "AUTOINCREMENT"
    type_map = {
        "integer":     "INTEGER",
        "float":       "REAL",
        "boolean":     "INTEGER",
        "string":      "VARCHAR",
        "text":        "TEXT",
        "datetime":    "DATETIME",
        "primary_key": "INTEGER",
    }
    upsert = "INSERT OR REPLACE INTO {t} ({cols}) VALUES ({ph})"
    insert_returning = None
    supports_if_not_exists = True
```

### 2.3 PostgreSQLDialect

```python
class PostgreSQLDialect(Dialect):
    name              = "postgresql"
    param_style       = "%s"
    quote_identifier  = '"name"'
    auto_increment_sql = "SERIAL"
    type_map = {
        "integer":     "INTEGER",
        "float":       "DOUBLE PRECISION",
        "boolean":     "BOOLEAN",
        "string":      "VARCHAR",
        "text":        "TEXT",
        "datetime":    "TIMESTAMP",
        "primary_key": "SERIAL",
    }
    upsert = "INSERT INTO {t} ({cols}) VALUES ({ph}) ON CONFLICT ({conflict}) DO UPDATE SET {updates}"
    insert_returning = "INSERT INTO {t} ({cols}) VALUES ({ph}) RETURNING *"
    supports_if_not_exists = True
```

Las columnas conflict se actualizan con `EXCLUDED.col` (sintaxis PostgreSQL).

### 2.4 MySQLDialect

```python
class MySQLDialect(Dialect):
    name              = "mysql"
    param_style       = "%s"
    quote_identifier  = "`name`"
    auto_increment_sql = "AUTO_INCREMENT"
    type_map = {
        "integer":     "INTEGER",
        "float":       "DOUBLE",
        "boolean":     "TINYINT(1)",
        "string":      "VARCHAR",
        "text":        "TEXT",
        "datetime":    "DATETIME",
        "primary_key": "INTEGER",
    }
    upsert = "REPLACE INTO {t} ({cols}) VALUES ({ph})"
    insert_returning = None
    supports_if_not_exists = False   # MySQL no soporta IF NOT EXISTS en índices
```

---

## 3. Mockup: Cómo el Sistema de Dialectos Decide el SQL

### 3.1 Mapeo de Tipos

```
Campo: BooleanField(name="is_active")
                  │
                  ├── SQLiteDialect.type_map["boolean"] = "INTEGER"
                  │     → "is_active INTEGER NOT NULL"
                  │
                  ├── PostgreSQLDialect.type_map["boolean"] = "BOOLEAN"
                  │     → "is_active BOOLEAN NOT NULL"
                  │
                  └── MySQLDialect.type_map["boolean"] = "TINYINT(1)"
                        → "is_active TINYINT(1) NOT NULL"
```

```
Campo: PrimaryKeyField(name="id")
                  │
                  ├── SQLiteDialect:  "id INTEGER PRIMARY KEY AUTOINCREMENT"
                  │
                  ├── PostgreSQLDialect:  "id SERIAL PRIMARY KEY"
                  │     (SERIAL es un pseudo-tipo que crea un INTEGER + secuencia)
                  │
                  └── MySQLDialect:  "id INTEGER PRIMARY KEY AUTO_INCREMENT"
```

```
Campo: DateTimeField(name="created_at")
                  │
                  ├── SQLiteDialect:  "created_at DATETIME NOT NULL"
                  │
                  ├── PostgreSQLDialect:  "created_at TIMESTAMP NOT NULL"
                  │
                  └── MySQLDialect:  "created_at DATETIME NOT NULL"
```

### 3.2 Estilo de Placeholders en Consultas

```
Condición: age > 18
                  │
                  ├── Condition.compile()  [clauses.py:31]
                  │       Antes: "age > ?"
                  │
                  └── Con dialecto: consulta adapter.param_style
                        │
                        ├── SQLite:   "age > ?"      params = [18]
                        ├── Postgres: "age > %s"     params = [18]
                        └── MySQL:    "age > %s"     params = [18]
```

### 3.3 UPSERT en `save()`

Cuando un modelo ya tiene PK y se llama a `save()`:

```
save()  →  detecta que PK tiene valor  →  UPDATE o UPSERT
                  │
                  ├── SQLiteDialect.compile_upsert():
                  │     "INSERT OR REPLACE INTO user (id, name, email)
                  │      VALUES (?, ?, ?)"
                  │
                  ├── PostgreSQLDialect.compile_upsert():
                  │     "INSERT INTO user (id, name, email)
                  │      VALUES (%s, %s, %s)
                  │      ON CONFLICT (id) DO UPDATE SET
                  │        name = EXCLUDED.name,
                  │        email = EXCLUDED.email"
                  │
                  └── MySQLDialect.compile_upsert():
                        "REPLACE INTO user (id, name, email)
                         VALUES (%s, %s, %s)"
```

### 3.4 INSERT con RETURNING

Cuando se inserta un nuevo registro y se necesita el ID generado:

```
SQLite:       cursor.lastrowid          (propiedad del cursor)
PostgreSQL:   "INSERT INTO user (...) VALUES (%s) RETURNING *"
              → se obtiene el ID desde la fila retornada
MySQL:        cursor.lastrowid          (igual que SQLite)
```

### 3.5 Quote de Identificadores

```
quote_identifier("user")
                  │
                  ├── SQLite:     "user"
                  ├── PostgreSQL: "user"
                  └── MySQL:      `user`
```

---

## 4. Adaptador PostgreSQL — `src/orm/db/postgresql.py`

### Arquitectura

```
PostgreSQLAdapter
  ├── _dialect: PostgreSQLDialect
  ├── _pool: ThreadedConnectionPool (psycopg2.pool)
  ├── _local: threading.local()
  ├── _lock: threading.Lock()
  │
  ├── __init__(dsn=None, host, port, dbname, user, password, minconn, maxconn)
  │     Si dsn está presente, parsea la URL.
  │     Si no, usa parámetros individuales.
  │
  ├── connect() → verifica conexión con "SELECT 1"
  ├── execute(query, params) → auto-commit
  ├── _execute_no_commit(query, params) → sin commit
  ├── query(query, params) → solo lectura
  ├── commit() / rollback()
  ├── close() → cierra pool
  ├── set_isolation_level(level)
  └── get_dialect() → PostgreSQLDialect
```

### Pool de Conexiones

```python
def _get_pool(self):
    if self._pool is None:
        import psycopg2.pool
        with self._lock:
            if self._pool is None:
                self._pool = psycopg2.pool.ThreadedConnectionPool(
                    self._minconn, self._maxconn,
                    host=self.host, port=self.port,
                    dbname=self.dbname,
                    user=self.user, password=self.password,
                )
    return self._pool
```

Cada hilo obtiene su propia conexión del pool vía `_get_connection()`:

```python
def _get_connection(self):
    if not hasattr(self._local, "connection") or self._local.connection is None:
        pool = self._get_pool()
        self._local.connection = pool.getconn()
    return self._local.connection
```

Las conexiones se devuelven al pool con `_release_if_held()` en `close()`.

---

## 5. Adaptador MySQL — `src/orm/db/mysql.py`

### Arquitectura

```
MySQLAdapter
  ├── _dialect: MySQLDialect
  ├── _local: threading.local()
  ├── _lock: threading.Lock()
  │
  ├── __init__(dsn=None, host, port, dbname, user, password, charset)
  │     charset default: "utf8mb4"
  │
  ├── connect() → verifica con "SELECT 1"
  ├── execute(query, params) → auto-commit
  ├── _execute_no_commit(query, params) → sin commit
  ├── query(query, params) → solo lectura
  ├── commit() / rollback()
  ├── close() → cierra conexión del hilo
  ├── set_isolation_level(level)  → sintaxis MySQL
  └── get_dialect() → MySQLDialect
```

### Conexión por hilo

```python
def _get_connection(self):
    if not hasattr(self._local, "connection") or self._local.connection is None:
        import pymysql
        self._local.connection = pymysql.connect(
            host=self.host, port=self.port,
            database=self.dbname,
            user=self.user, password=self.password,
            charset=self._charset,
            cursorclass=pymysql.cursors.Cursor,
        )
    return self._local.connection
```

### `set_isolation_level()`

```python
def set_isolation_level(self, level: str) -> None:
    level = level.upper()
    valid = {"READ UNCOMMITTED", "READ COMMITTED", "REPEATABLE READ", "SERIALIZABLE"}
    if level not in valid:
        raise ValueError(f"Invalid isolation level: {level}")
    self.execute(f"SET SESSION TRANSACTION ISOLATION LEVEL {level}")
```

---

## 6. Registry y Factory por URL — `src/orm/db/registry.py`

### 6.1 `create_adapter(url, **kwargs)`

Parsea una URL y construye el adaptador correspondiente:

```python
def create_adapter(url, **kwargs):
    parsed = urlparse(url)
    scheme = parsed.scheme

    if scheme == "sqlite":
        # sqlite:///data/mi_app.db → SQLiteAdapter
        db_path = parsed.path.lstrip("/") or ":memory:"
        ...

    if scheme in ("postgresql", "postgres"):
        # postgresql://user:pass@host:5432/dbname → PostgreSQLAdapter
        return PostgreSQLAdapter(dsn=url, **kwargs)

    if scheme in ("mysql", "mysql+pymysql"):
        # mysql://user:pass@host:3306/dbname → MySQLAdapter
        return MySQLAdapter(dsn=url, **kwargs)

    raise ValueError(f"Unsupported database scheme: {scheme}")
```

### 6.2 Registry de adaptadores

```python
_adapter_registry = {
    "sqlite": SQLiteAdapter,
    "postgresql": PostgreSQLAdapter,
    "postgres": PostgreSQLAdapter,
    "mysql": MySQLAdapter,
}

def register_adapter(scheme, adapter_class):
    _adapter_registry[scheme] = adapter_class

def get_adapter_class(scheme):
    return _adapter_registry.get(scheme)
```

### 6.3 Mockup: Uso Final

```python
# Antes (solo SQLite):
from src.orm import SQLiteAdapter, configure
db = SQLiteAdapter(db_directory="data", db_name="mi_app")
configure(db)

# Ahora (cualquier motor):
from src.orm import create_adapter

# SQLite
db = create_adapter("sqlite:///data/mi_app.db")

# PostgreSQL
db = create_adapter("postgresql://user:pass@localhost:5432/mydb")

# MySQL
db = create_adapter("mysql://user:pass@localhost:3306/mydb")

db.connect()
configure(db)
```

---

## 7. Mejoras a `DatabaseAdapter` — `src/orm/db/base.py`

### 7.1 Antes (committed)

```python
class DatabaseAdapter(ABC):
    @abstractmethod
    def connect(self): ...
    @abstractmethod
    def execute(self, query, params): ...
    @abstractmethod
    def query(self, query, params): ...
    @abstractmethod
    def commit(self): ...
    @abstractmethod
    def rollback(self): ...
    @abstractmethod
    def close(self): ...

    def transaction(self):
        return TransactionContext(self)
```

### 7.2 Después (con mejoras)

```python
class DatabaseAdapter(ABC):
    _dialect: Optional[Dialect] = None

    # --- Métodos abstractos (sin cambios) ---
    @abstractmethod
    def connect(self): ...
    @abstractmethod
    def execute(self, query, params): ...
    @abstractmethod
    def query(self, query, params): ...
    @abstractmethod
    def commit(self): ...
    @abstractmethod
    def rollback(self): ...
    @abstractmethod
    def close(self): ...

    # --- NUEVOS métodos abstractos ---
    @abstractmethod
    def get_dialect(self) -> Dialect: ...

    # --- NUEVAS propiedades ---
    @property
    def param_style(self) -> str:
        return self.get_dialect().param_style

    # --- NUEVOS métodos para transacciones ---
    def begin(self):
        self._execute_no_commit("BEGIN")

    def savepoint(self, name):
        q = self.get_dialect().quote_identifier(name)
        self._execute_no_commit(f"SAVEPOINT {q}")

    def rollback_to_savepoint(self, name):
        q = self.get_dialect().quote_identifier(name)
        self._execute_no_commit(f"ROLLBACK TO SAVEPOINT {q}")

    def release_savepoint(self, name):
        q = self.get_dialect().quote_identifier(name)
        self._execute_no_commit(f"RELEASE SAVEPOINT {q}")

    def set_isolation_level(self, level):
        raise NotImplementedError(...)

    def nested_transaction(self):
        return NestedTransactionContext(self)

    # --- transaction() mejorado (ahora llama a begin/commit/rollback) ---
    def transaction(self):
        return TransactionContext(self)
```

### 7.3 `TransactionContext` mejorado

```python
class TransactionContext:
    def __enter__(self):
        self.db.begin()
        self._active = True
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if not self._active:
            return False
        self._active = False
        if exc_type is None:
            self.db.commit()
        else:
            try:
                self.db.rollback()
            except Exception:
                pass
        return False
```

### 7.4 `NestedTransactionContext` (NUEVO)

```python
class NestedTransactionContext:
    def __enter__(self):
        import uuid
        self._name = f"sp_{uuid.uuid4().hex[:8]}"
        self.db.savepoint(self._name)
        self._active = True
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if not self._active:
            return False
        self._active = False
        if exc_type is None:
            self.db.release_savepoint(self._name)
        else:
            try:
                self.db.rollback_to_savepoint(self._name)
            except Exception:
                pass
        return False
```

### 7.5 Método auxiliar `_execute_no_commit`

Agregado como método concreto en `DatabaseAdapter` para que las subclases puedan sobrescribirlo si es necesario:

```python
def _execute_no_commit(self, query, params=None):
    return self.execute(query, params)
```

`PostgreSQLAdapter` y `MySQLAdapter` lo sobrescriben para ejecutar sin auto-commit.

---

## 8. Mejoras a `SQLiteAdapter` — `src/orm/db/sqlite.py`

### 8.1 Cambios principales

| Aspecto | Antes (committed) | Después |
|---|---|---|
| `_dialect` | No existía | `self._dialect = SQLiteDialect()` |
| `get_dialect()` | No existía | Retorna `self._dialect` |
| `sqlite3.connect(...)` | Sin `isolation_level` | `isolation_level=None` (control manual) |
| `execute()` | Auto-commit interno | Ya NO hace commit (se delega al llamador) |
| `_execute_no_commit()` | No existía | Hereda de `DatabaseAdapter` (usa `execute()`) |
| `set_isolation_level()` | No existía | Vía `PRAGMA read_uncommitted` |

### 8.2 Execute — Antes vs Después

```python
# ANTES:
def execute(self, query, params=None):
    with self._lock:
        cursor = connection.cursor()
        cursor.execute(query, params)
        connection.commit()    # ← auto-commit
        return cursor

# DESPUÉS:
def execute(self, query, params=None):
    with self._lock:
        cursor = connection.cursor()
        cursor.execute(query, params)
        return cursor          # ← sin commit
```

Esto permite que `transaction()` y `begin()`/`commit()` controlen el ciclo transaccional correctamente.

### 8.3 `set_isolation_level()`

```python
def set_isolation_level(self, level):
    valid = {"READ UNCOMMITTED", "READ COMMITTED", "REPEATABLE READ", "SERIALIZABLE"}
    if level not in valid:
        raise ValueError(f"Invalid isolation level: {level}")
    if level == "READ UNCOMMITTED":
        self.execute("PRAGMA read_uncommitted = 1")
    else:
        self.execute("PRAGMA read_uncommitted = 0")
```

---

## 9. Mockup Visual: Ciclo Completo Multi-Engine

```
CÓDIGO DEL USUARIO:
┌─────────────────────────────────────────────────────────────────────────┐
│ db = create_adapter("postgresql://user:pass@localhost:5432/mi_app")    │
│ db.connect()                                                            │
│ configure(db)                                                           │
│                                                                         │
│ class User(Model):                                                      │
│     id = PrimaryKeyField()                                              │
│     name = CharField(max_length=100)                                    │
│     is_active = BooleanField(default=True)                              │
│                                                                         │
│ User.create_table()                                                     │
│ User.objects.create(name="Alice", is_active=True)                       │
│ users = User.objects.filter(is_active=True).all()                       │
└─────────────────────────────────────────────────────────────────────────┘
        │                                               motor = "postgresql"
        v
┌─────────────────────────────────────────────────────────────────────────┐
│ create_adapter()  →  registry.py                                       │
│   scheme="postgresql" → PostgreSQLAdapter(dsn=...)                     │
│     │                                                                  │
│     └── self._dialect = PostgreSQLDialect()                           │
│         ├── param_style = "%s"                                        │
│         ├── type_map["boolean"] = "BOOLEAN"                          │
│         ├── type_map["primary_key"] = "SERIAL"                       │
│         └── compile_upsert() → ON CONFLICT DO UPDATE                  │
└─────────────────────────────────────────────────────────────────────────┘
        │
        v
┌─────────────────────────────────────────────────────────────────────────┐
│ User.create_table()   [_methods.py:53]                                 │
│                                                                         │
│   field.to_sql() para cada campo:                                      │
│     PrimaryKeyField: "id SERIAL PRIMARY KEY"                            │
│     CharField:       "name VARCHAR(100) NOT NULL"                       │
│     BooleanField:    "is_active BOOLEAN NOT NULL"                       │
│                                                                         │
│   → "CREATE TABLE IF NOT EXISTS user (id SERIAL PRIMARY KEY,           │
│        name VARCHAR(100) NOT NULL, is_active BOOLEAN NOT NULL)"        │
└─────────────────────────────────────────────────────────────────────────┘
        │
        v
┌─────────────────────────────────────────────────────────────────────────┐
│ PostgreSQLAdapter.execute(sql)                                         │
│   pool.getconn() → connection psycopg2                                 │
│   cursor.execute("CREATE TABLE IF NOT EXISTS user (...)", [])          │
│   conn.commit()                                                        │
└─────────────────────────────────────────────────────────────────────────┘
        │
        v
┌─────────────────────────────────────────────────────────────────────────┐
│ User.objects.create(name="Alice", is_active=True)                      │
│   → User(name="Alice", is_active=True).save()                         │
│                                                                         │
│ save() → INSERT (no tiene PK aún)                                      │
│   PostgreSQLDialect.compile_insert_returning():                         │
│   "INSERT INTO user (name, is_active) VALUES (%s, %s) RETURNING *"    │
│                                                                         │
│ PostgreSQLAdapter.execute(sql, ["Alice", True])                        │
│   → cursor.fetchone() → {"id": 1, "name": "Alice", "is_active": True} │
│   → se asigna user.id = 1                                              │
└─────────────────────────────────────────────────────────────────────────┘
        │
        v
┌─────────────────────────────────────────────────────────────────────────┐
│ User.objects.filter(is_active=True).all()                              │
│   → QuerySet → QueryBuilder.compile()                                  │
│                                                                         │
│   Condition.compile() → consulta dialect.param_style:                   │
│     "user.is_active = %s"  params: [True]                              │
│                                                                         │
│   → "SELECT * FROM user WHERE user.is_active = %s"                    │
│                                                                         │
│ PostgreSQLAdapter.query(sql, [True])                                    │
│   → cursor.fetchall() → [<Row: id=1, name="Alice", ...>]              │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 10. Mockup: Transacciones Anidadas con Savepoints

```
with db.transaction():                  → db.begin()
                                          │
    user.save()                         → INSERT INTO user ...
                                          │
    with db.nested_transaction():       → db.savepoint("sp_a1b2c3d4")
        post.save()                       │
        # ...                             │
        if error:                         │
            raise                        │
                                          ▼
                                     db.rollback_to_savepoint("sp_a1b2c3d4")
                                          │
    # si nested falló, outer sigue       │
    other.save()                         │
                                          │
                                          ▼
→ db.commit()  (todo)  o  db.rollback() (nada)
```

Cada savepoint genera un UUID único:

```python
self._name = f"sp_{uuid.uuid4().hex[:8]}"   # ej: "sp_a1b2c3d4"
```

El quoting del nombre se hace con el dialecto:

```python
def savepoint(self, name):
    q = self.get_dialect().quote_identifier(name)
    self._execute_no_commit(f"SAVEPOINT {q}")
```

---

## 11. Mockup: Comparativa de SQL Generado por Motor

### CREATE TABLE

```sql
-- SQLite
CREATE TABLE IF NOT EXISTS user (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(100) NOT NULL,
    is_active INTEGER NOT NULL
);

-- PostgreSQL
CREATE TABLE IF NOT EXISTS user (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    is_active BOOLEAN NOT NULL
);

-- MySQL
CREATE TABLE IF NOT EXISTS user (
    id INTEGER PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(100) NOT NULL,
    is_active TINYINT(1) NOT NULL
);
```

### INSERT (nuevo registro)

```sql
-- SQLite
INSERT INTO user (name, is_active) VALUES (?, ?)
-- cursor.lastrowid → obtiene el ID

-- PostgreSQL
INSERT INTO user (name, is_active) VALUES (%s, %s) RETURNING *
-- cursor.fetchone()["id"] → obtiene el ID

-- MySQL
INSERT INTO user (name, is_active) VALUES (%s, %s)
-- cursor.lastrowid → obtiene el ID
```

### UPSERT (registro existente)

```sql
-- SQLite
INSERT OR REPLACE INTO user (id, name, is_active) VALUES (?, ?, ?)

-- PostgreSQL
INSERT INTO user (id, name, is_active) VALUES (%s, %s, %s)
ON CONFLICT (id) DO UPDATE SET
    name = EXCLUDED.name,
    is_active = EXCLUDED.is_active

-- MySQL
REPLACE INTO user (id, name, is_active) VALUES (%s, %s, %s)
```

### SELECT con filtro

```sql
-- SQLite
SELECT * FROM user WHERE name LIKE ? AND is_active = ?

-- PostgreSQL
SELECT * FROM user WHERE name LIKE %s AND is_active = %s

-- MySQL
SELECT * FROM user WHERE name LIKE %s AND is_active = %s
```

### LIMIT / OFFSET

```sql
-- SQLite
SELECT * FROM user LIMIT 10 OFFSET 20

-- PostgreSQL
SELECT * FROM user LIMIT 10 OFFSET 20

-- MySQL
SELECT * FROM user LIMIT 10 OFFSET 20
```

### CREATE INDEX

```sql
-- SQLite
CREATE UNIQUE INDEX IF NOT EXISTS idx_user_email ON user(email)

-- PostgreSQL
CREATE UNIQUE INDEX IF NOT EXISTS idx_user_email ON user(email)

-- MySQL
CREATE UNIQUE INDEX idx_user_email ON user(email)
-- NOTA: MySQL NO soporta IF NOT EXISTS en CREATE INDEX
-- El dialecto tiene supports_if_not_exists = False
```

---

## 12. Lo que Falta por Conectar

El sistema de dialectos y los nuevos adaptadores están implementados, pero varias partes del ORM aún generan SQL hardcodeado para SQLite. Estas son las conexiones pendientes:

### 12.1 `_methods.py` — UPSERT y DDL hardcodeados

```python
# Actual (SQLite hardcodeado):
query = f"INSERT OR REPLACE INTO {self._table_name} ({field_names}) VALUES ({placeholders})"

# Debería ser:
dialect = self.__class__._db.get_dialect()
query = dialect.compile_upsert(self._table_name, list(fields.keys()), [self._pk_field])
```

```python
# Actual (SQLite hardcodeado):
query = f"CREATE TABLE IF NOT EXISTS {cls._table_name} ({', '.join(all_items)})"

# Debería usar dialect.type_map para los tipos y dialect.auto_increment_sql para PK
```

### 12.2 `fields.py` — `to_sql()` sin dialecto

```python
# Actual:
class BooleanField(Field):
    def to_sql(self):
        return f"{self.name} BOOLEAN ..."    # hardcodeado

# Debería aceptar dialect:
    def to_sql(self, dialect=None):
        sql_type = dialect.type_map["boolean"] if dialect else "BOOLEAN"
        return f"{self.name} {sql_type} ..."
```

### 12.3 `query_builder/clauses.py` — Placeholders hardcodeados

```python
# Actual (hardcodeado):
class Condition:
    def compile(self):
        return f"{self.field} {self.operator} ?", [self.value]

# Debería recibir el param_style del dialecto:
    def compile(self, param_style="?"):
        return f"{self.field} {self.operator} {param_style}", [self.value]
```

### 12.4 `migrations/inspector.py` — PRAGMAs solo SQLite

```python
# Actual:
class Inspector:
    def get_table_names(self):
        cursor = self.db.query("SELECT name FROM sqlite_master WHERE type='table'")

# Debería tener implementaciones por motor:
# SQLite:     sqlite_master + PRAGMAs
# PostgreSQL: INFORMATION_SCHEMA.TABLES + INFORMATION_SCHEMA.COLUMNS
# MySQL:      INFORMATION_SCHEMA.TABLES + INFORMATION_SCHEMA.COLUMNS
```

### 12.5 `migrations/operations.py` — DDL SQLite-specific

```python
# Actual (hardcodeado):
class CreateTable:
    def up(self, db):
        if c.primary_key and c.type.upper() == "INTEGER":
            parts.append("PRIMARY KEY AUTOINCREMENT")  # SQLite only

# Debería usar db.get_dialect().auto_increment_sql()
```

### 12.6 `query.py` — Placeholders en prefetch y subqueries

```python
# Actual (hardcodeado):
placeholders = ",".join("?" for _ in pks)    # línea 385, 424

# Debería usar el dialecto del adapter:
placeholders = ",".join(db.param_style for _ in pks)
```

---

## 13. Resumen de la Arquitectura Post-Mejoras

```
src/orm/
├── db/
│   ├── __init__.py       → Exporta DatabaseAdapter, SQLiteAdapter,
│   │                        PostgreSQLAdapter, MySQLAdapter,
│   │                        Dialect, SQLiteDialect, PostgreSQLDialect,
│   │                        MySQLDialect, create_adapter, register_adapter
│   │
│   ├── base.py            → DatabaseAdapter (ABC con dialect, savepoints,
│   │                        transacciones anidadas, isolation level)
│   │
│   ├── dialect.py         → Dialect (ABC) + SQLiteDialect + PostgreSQLDialect
│   │   (NUEVO)               + MySQLDialect
│   │
│   ├── sqlite.py          → SQLiteAdapter (refactorizado con SQLiteDialect)
│   │
│   ├── postgresql.py      → PostgreSQLAdapter (pool de conexiones psycopg2)
│   │   (NUEVO)
│   │
│   ├── mysql.py           → MySQLAdapter (conexiones pymysql por hilo)
│   │   (NUEVO)
│   │
│   └── registry.py        → create_adapter(url) + register_adapter() + get_adapter_class()
│       (NUEVO)
```

---

## 14. Dependencias Externas

Archivo `requirements.txt` (NUEVO):

```
psycopg2-binary>=2.9.9    # PostgreSQL adapter
pymysql>=1.1.1            # MySQL adapter
```

Ambas son dependencias opcionales: si no se usa PostgreSQL o MySQL, no es necesario instalarlas. SQLite sigue funcionando sin dependencias externas.

---

*Documento generado basado en los cambios sin commit respecto al commit `7a10a27`.*
