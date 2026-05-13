# Cómo Funciona el ORM — Flujo Completo (hasta commit 7a10a27)

## 1. Arquitectura General

El ORM está organizado en 4 capas que se comunican secuencialmente:

```
+-----------------------------------------------------------+
|                         CAPA 1: USUARIO                    |
|  main.py / ejemplo.py                                      |
|  define modelos, hace consultas                            |
+-----------------------------------------------------------+
          |  configure()  |  class User(Model)  |  User.objects...
          v               v                      v
+-----------------------------------------------------------+
|              CAPA 2: ORM (src/orm/)                        |
|  +----------+  +---------+  +----------+  +------------+   |
|  | base.py  |  | setup.py|  | manager  |  |  query.py  |   |
|  |  Model   |  | setup_  |  | Model-   |  |  QuerySet  |   |
|  |          |  | model() |  | Manager  |  |  Q()       |   |
|  +----------+  +---------+  +----------+  +------------+   |
|                      |                           |          |
|                      v                           v          |
|  +------------+  +----------+  +------------------------+   |
|  | fields.py  |  | config.py|  | query_builder/         |   |
|  | Field      |  |configure |  | builder.py + clauses.py|   |
|  | to_sql()   |  |get_defaul|  | QueryBuilder.compile() |   |
|  +------------+  +----------+  +------------------------+   |
+-----------------------------------------------------------+
          |  db.execute(query, params)
          v
+-----------------------------------------------------------+
|           CAPA 3: ADAPTADOR DE BASE DE DATOS               |
|  src/orm/db/                                               |
|  +----------------+  +-------------------+                 |
|  | base.py        |  | sqlite.py         |                 |
|  | DatabaseAdapter|  | SQLiteAdapter     |                 |
|  | (ABC)          |  | implementa execute,|                |
|  |                |  | query, commit, etc |                |
|  +----------------+  +-------------------+                 |
+-----------------------------------------------------------+
          |  sqlite3.connect / cursor.execute
          v
+-----------------------------------------------------------+
|              CAPA 4: SQLite (python estándar)              |
|  sqlite3.Connection → archivo .db en disco                 |
+-----------------------------------------------------------+
```

---

## 2. Punto de Entrada: Configuración

### 2.1 `configure(db_adapter)` — `src/orm/config.py`

```python
_default_db: Optional[DatabaseAdapter] = None

def configure(db_adapter: DatabaseAdapter) -> None:
    global _default_db
    _default_db = db_adapter

def get_default_db() -> Optional[DatabaseAdapter]:
    return _default_db
```

Es un singleton global. Se llama **una vez** al inicio del programa:

```python
from src.orm import SQLiteAdapter, configure

db = SQLiteAdapter(db_directory="data", db_name="mi_app")
db.connect()
configure(db)
```

### 2.2 `SQLiteAdapter` — `src/orm/db/sqlite.py`

- Cada hilo obtiene su propia conexión (`threading.local()`).
- Las escrituras se serializan con `threading.Lock()`.
- `execute()` hace auto-commit. `query()` no.

```python
class SQLiteAdapter(DatabaseAdapter):
    def __init__(self, db_directory=None, db_name=None, db_name_extension="db"):
        self.database_path = os.path.join(db_directory, f"{db_name}.{db_name_extension}")
        self._local = threading.local()
        self._lock = threading.Lock()
        ...

    def execute(self, query, params=None):
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(query, params)
            conn.commit()          # auto-commit
            return cursor

    def query(self, query, params=None):
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(query, params)
            return cursor           # sin commit
```

---

## 3. Definición de Modelos: 3 Enfoques

### Enfoque 1: Herencia clásica

```python
class User(Model):
    _table_name = "users"

    id = PrimaryKeyField()
    name = CharField(max_length=100)
    email = CharField(max_length=255, unique=True)
```

### Enfoque 2: Decorador `@model` + field decorators en asignación

```python
@model
class Product:
    id = primary_key()
    name = char_field(max_length=200)
    price = integer_field()
```

### Enfoque 3: Decorador `@model` + field decorators sobre métodos

```python
@model(table_name="tags")
class Tag:
    @primary_key
    def id(self): ...

    @char_field(max_length=50, unique=True)
    def name(self): ...
```

---

## 4. El Proceso `__init_subclass__` → `setup_model()`

Este es el **corazón de la inicialización**. Ocurre automáticamente cuando Python procesa la definición de la clase.

### Diagrama de flujo

```
Python define class User(Model)
        |
        v
__init_subclass__()  [base.py:21]
        |
        v
setup_model(cls)     [setup.py:10]
        |
        +---> Asigna _table_name  (default: clase en minúsculas)
        |
        +---> Itera cls.__dict__:
        |       - ManyToManyField → _m2m_fields
        |       - ForeignKey      → _fk_fields + _fields[fk_column]
        |       - Field           → _fields[name] + __set_name__
        |
        +---> Crea ModelManager(cls) como cls.objects
        |
        +---> Resuelve _db:
        |       ¿db explícito? → úsalo
        |       ¿get_default_db()? → úsalo
        |       si no → ModelError
        |
        +---> _collect_indexes(cls)  → _indexes
        +---> _collect_constraints(cls) → _constraints
        |
        +---> registry.register(cls)
```

### Código real (simplificado)

```python
# src/orm/base.py
class Model:
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        setup_model(cls)

    def __init__(self, **kwargs):
        init_model(self, **kwargs)
```

```python
# src/orm/setup.py
def setup_model(cls, *, table_name=None, db=None):
    if table_name:
        cls._table_name = table_name
    elif not hasattr(cls, "_table_name"):
        cls._table_name = cls.__name__.lower()

    cls._fields = {}
    cls._fk_fields = {}
    cls._m2m_fields = {}

    for name, attr in list(cls.__dict__.items()):
        if isinstance(attr, ManyToManyField):
            attr.contribute(cls, name)
            cls._m2m_fields[name] = attr
        elif isinstance(attr, ForeignKey):
            cls._fields[attr.fk_column] = attr
            cls._fk_fields[name] = attr
            attr._setup_reverse(cls)
        elif isinstance(attr, Field):
            cls._fields[name] = attr
            attr.__set_name__(cls, name)

    cls.objects = ModelManager(cls)

    if db is not None:
        cls._db = db
    elif not hasattr(cls, "_db"):
        default_db = get_default_db()
        if default_db is None:
            raise ModelError(...)
        cls._db = default_db

    _collect_indexes(cls)
    _collect_constraints(cls)
    registry.register(cls)
```

### ¿Qué queda configurado en la clase?

| Atributo | Contenido |
|---|---|
| `cls._table_name` | Nombre de la tabla SQL |
| `cls._fields` | `dict[str, Field]` — todos los campos |
| `cls._fk_fields` | `dict[str, ForeignKey]` — solo FKs |
| `cls._m2m_fields` | `dict[str, ManyToManyField]` — solo M2Ms |
| `cls._db` | `DatabaseAdapter` a usar |
| `cls.objects` | `ModelManager` — entry point de consultas |
| `cls._indexes` | Lista de `Index` |
| `cls._constraints` | Lista de `CheckConstraint` / `UniqueConstraint` |

---

## 5. Fields: Generación de DDL

### Jerarquía

```
Field
  ├── PrimaryKeyField   → INTEGER PRIMARY KEY AUTOINCREMENT
  ├── CharField         → VARCHAR(n) [NOT NULL] [UNIQUE]
  ├── IntegerField      → INTEGER [NOT NULL] [UNIQUE]
  ├── FloatField        → REAL [NOT NULL] [UNIQUE]
  ├── BooleanField      → BOOLEAN [NOT NULL]
  ├── DateTimeField     → DATETIME [NOT NULL]
  └── TextField         → TEXT [NOT NULL] [UNIQUE]
```

Cada campo implementa `to_sql()`:

```python
class CharField(Field):
    def to_sql(self):
        sql = f"{self.name} VARCHAR({self.max_length})"
        if not self.null:
            sql += " NOT NULL"
        if self.unique:
            sql += " UNIQUE"
        return sql
```

### Relaciones: ForeignKey y ManyToManyField

- `ForeignKey(to)` → agrega columna `{name}_id INTEGER REFERENCES {to}(pk)` + descriptor para lazy loading
- `OneToOneField(to)` → lo mismo + UNIQUE
- `ManyToManyField(to)` → NO agrega columna en la tabla actual. Crea una **tabla pivote** `{owner_table}_{name}` con columnas `{owner}_id`, `{to}_id` y PK compuesta

---

## 6. Ciclo de una Consulta: `User.objects.filter(age__gt=18).all()`

### Diagrama paso a paso

```
User.objects.filter(age__gt=18).all()
        |
        | 1. ModelManager.filter()
        v
+-------------------+
| ModelManager      |  [manager.py:16]
| self.model = User |
+-------------------+
        |
        | Crea un QuerySet(User) y llama .filter(age__gt=18)
        v
+-------------------+
| QuerySet.filter() |  [query.py:195]
+-------------------+
        |
        | 2. _build_condition("age__gt", 18, operator_map)
        |    partes = ["age", "gt"]
        |    field = "age", op_key = "gt" → operator = ">"
        |    retorna ("user.age", ">", 18)
        |
        | 3. _builder._where.add("user.age", ">", 18)
        v
+---------------------------+
| Where.add(field,op,value) |  [clauses.py:54]
+---------------------------+
        |
        | Crea Condition("user.age", ">", 18) y lo guarda
        v
+---------------------------+
| Condition(field,op,value) |  [clauses.py:18]
+---------------------------+

--- Luego .all() ---

        |
        | 4. QuerySet.all()  [query.py:484]
        v
+-------------------+
| _build_query()    |  [query.py:473]
+-------------------+
        |
        | 5. QueryBuilder.compile()  [builder.py:82]
        v
+-------------------+
| compile()         |
+-------------------+
        |
        | Genera:
        |   SQL: "SELECT * FROM user WHERE user.age > ?"
        |   params: [18]
        v
+-------------------+
| CompiledQuery     |  (sql, params)
+-------------------+
        |
        | 6. self.model._db.query(sql, params)
        v
+-------------------+
| SQLiteAdapter     |  [sqlite.py:59]
| .query()          |
+-------------------+
        |
        | cursor.execute("SELECT * FROM user WHERE user.age > ?", [18])
        | sqlite3.Connection
        v
+-------------------+
| SQLite engine      |
| (archivo .db)     |
+-------------------+
        |
        | cursor.fetchall() → filas como diccionarios
        v
+-------------------+
| 7. Construir      |
|    instancias     |
+-------------------+
        |
        | [User(id=1, name="Alice", age=30), User(id=2, name="Bob", age=25)]
        v
      Resultado devuelto al usuario
```

### Flujo detallado de `compile()` en QueryBuilder

```python
def compile(self):                       # builder.py:82
    sql = f"SELECT {self._select.compile()} FROM {self._from}"
    #                  │                          │
    #                  ▼                          ▼
    #               Select.compile()        model._table_name
    #               retorna "*"             ej: "user"
    #
    for j in self._joins:
        sql += f" {j.compile()}"           # LEFT JOIN ... ON ...
    #
    params = []
    if self._where:
        where_sql, where_params = self._where.compile()
        if where_sql:
            sql += f" WHERE {where_sql}"
            params = where_params
    #           │
    #           ▼
    #    Where.compile():
    #      Condition("user.age", ">", 18)
    #        → "user.age > ?", [18]
    #
    if self._order_by.fields:
        sql += f" ORDER BY {self._order_by.compile()}"
    #
    if self._limit is not None:
        sql += f" LIMIT {self._limit.value}"
    if self._offset is not None:
        sql += f" OFFSET {self._offset.value}"
    #
    return CompiledQuery(sql, params)
```

---

## 7. Operaciones CRUD

### 7.1 Crear

```python
# Vía manager
user = User.objects.create(name="Alice", email="a@e.com")

# Vía instancia + save
user = User(name="Bob", email="b@e.com")
user.save()
```

`save()` en `_methods.py`:

```python
def save(self):
    fields = {k: v for k, v in self.__dict__.items()
              if k in self.__class__._fields}

    if self._pk_field and getattr(self, self._pk_field, None):
        # UPDATE
        pk_value = getattr(self, self._pk_field)
        set_fields = ", ".join([f"{k} = ?" for k in fields if k != self._pk_field])
        values = [fields[k] for k in fields if k != self._pk_field] + [pk_value]
        query = f"UPDATE {self._table_name} SET {set_fields} WHERE {self._pk_field} = ?"
        self.__class__._db.execute(query, values)
    else:
        # INSERT OR REPLACE
        field_names = ", ".join(fields.keys())
        placeholders = ", ".join(["?"] * len(fields))
        values = list(fields.values())
        query = f"INSERT OR REPLACE INTO {self._table_name} ({field_names}) VALUES ({placeholders})"
        cursor = self.__class__._db.execute(query, values)
        if self._pk_field:
            setattr(self, self._pk_field, cursor.lastrowid)
```

### 7.2 Leer

```python
User.objects.get(email="a@e.com")           # → instancia o DoesNotExist
User.objects.filter(age__gte=18).all()       # → lista
User.objects.first()                         # → primera o None
User.objects.count()                         # → entero
User.objects.exists()                        # → bool
```

### 7.3 Actualizar

```python
# Individual
user = User.objects.get(id=1)
user.name = "New Name"
user.save()

# Masiva
User.objects.filter(is_active=False).update(is_active=True)
```

`update()` en query.py:

```python
def update(self, **kwargs):
    set_clause = ", ".join([f"{k} = ?" for k in kwargs])
    set_params = list(kwargs.values())
    from_join_where, where_params = self._build_from_join_where()
    query = f"UPDATE {table_name} SET {set_clause} WHERE {pk_name} IN (SELECT {table_name}.{pk_name} {from_join_where})"
    cursor = self.model._db.execute(query, set_params + where_params)
    return cursor.rowcount
```

### 7.4 Eliminar

```python
# Individual
user = User.objects.get(id=1)
user.delete()

# Masiva
User.objects.filter(age__lt=18).delete()
```

### 7.5 Agregaciones

```python
stats = User.objects.aggregate(
    total="COUNT(*)",
    avg_age="AVG(age)",
    max_age="MAX(age)"
)
```

Genera:

```sql
SELECT COUNT(*) AS total, AVG(age) AS avg_age, MAX(age) AS max_age FROM user
```

---

## 8. Filtros: Operadores `__`

| Sintaxis | Operador SQL |
|---|---|
| `field=value` o `field__exact` | `=` |
| `field__ne` | `!=` |
| `field__gt` | `>` |
| `field__gte` | `>=` |
| `field__lt` | `<` |
| `field__lte` | `<=` |
| `field__like` | `LIKE` |
| `field__in` | `IN` |

### `Q` objects — lógica booleana

```python
User.objects.filter(
    Q(age__gt=18) & Q(is_active=True) | Q(name__like="Admin%")
)
```

Se convierten en árboles de `Where` anidados con AND/OR/NOT.

---

## 9. Relaciones y JOINs

### ForeignKey — Lazy loading automático

```python
class Post(Model):
    author = ForeignKey(User)

post = Post.objects.get(id=1)
post.author   # → hace User.objects.get(id=post.author_id) automáticamente
```

### select_related — JOIN eager loading

```python
posts = Post.objects.select_related("author").all()
```

Genera:

```sql
SELECT post.id AS id, post.title AS title, __author.id AS __author__id, ...
FROM post LEFT JOIN user AS __author ON post.author_id = __author.id
```

### prefetch_related — queries separadas

```python
users = User.objects.prefetch_related("posts").all()
```

Ejecuta 2 queries:
1. `SELECT * FROM user`
2. `SELECT * FROM post WHERE author_id IN (pk1, pk2, ...)`

Luego asigna cada post a su usuario en `__dict__["_posts_cached"]`.

### ManyToManyField

```python
class Student(Model):
    courses = ManyToManyField(Course)

s = Student.objects.get(id=1)
s.courses.add(course1)   # INSERT INTO student_courses ...
s.courses.all()           # SELECT via JOIN con tabla pivote
```

---

## 10. Creación de Tablas (`create_table()`)

```python
User.create_table()
```

Flujo en `_methods.py:53`:

```
create_table(cls)
  │
  ├── Itera cls._fields → field.to_sql()
  │     Ej: "id INTEGER PRIMARY KEY AUTOINCREMENT"
  │         "name VARCHAR(100) NOT NULL"
  │         "email VARCHAR(255) NOT NULL UNIQUE"
  │
  ├── Agrega CHECK constraints
  │
  ├── CREATE TABLE IF NOT EXISTS users (...)
  │
  ├── Crea tablas M2M: CREATE TABLE IF NOT EXISTS student_courses (...)
  │
  └── Crea índices: CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)
```

---

## 11. Sistema de Migraciones

### Flujo completo `make_migration()` — `migrations/autogen.py`

```
registry.getAll()          → listado de modelos
       │
ModelState.from_model()    → snapshot ideal de cada modelo
       │
Inspector(db)             → lee esquema REAL de la BD
  ├── get_table_names()    → sqlite_master
  ├── get_columns()        → PRAGMA table_info
  ├── get_indexes()        → PRAGMA index_list + index_info
  └── get_foreign_keys()   → PRAGMA foreign_key_list
       │
SchemaDiffer.diff()       → compara ideal vs real
  ├── tablas en modelo pero no en BD → CreateTable
  ├── tablas en ambos → diff columnas/índices → AddColumn/DropColumn/CreateIndex/DropIndex
  └── tablas en BD pero no en modelo → (sin implementar aún)
       │
Renderiza archivo .py con clase Migration:
    class Migration001(Migration):
        version = "001"
        def up(self):   ...
        def down(self): ...
```

### Operations ejecutables

| Operación | SQL generado |
|---|---|
| `CreateTable` | `CREATE TABLE IF NOT EXISTS ...` + `ALTER TABLE ADD COLUMN` para FKs + `CREATE INDEX` + tablas M2M |
| `DropTable` | `DROP TABLE IF EXISTS ...` |
| `AddColumn` | `ALTER TABLE ... ADD COLUMN ...` |
| `DropColumn` | `ALTER TABLE ... DROP COLUMN ...` (irreversible en SQLite) |
| `CreateIndex` | `CREATE [UNIQUE] INDEX IF NOT EXISTS ...` |
| `DropIndex` | `DROP INDEX IF EXISTS ...` |

### Aplicar migraciones con `Migrator`

```python
migrator = Migrator(db, migrations_dir="migrations")
migrator.migrate(target="latest")     # aplica pendientes
migrator.rollback(target="000")       # revierte hasta versión
```

El migrador mantiene una tabla `__migrations__` con las versiones aplicadas.

---

## 12. Transacciones

```python
with db.transaction():
    user = User.objects.create(name="Test", email="test@e.com")
    post = Post.objects.create(title="X", author_id=user.id)
    # si algo falla → rollback automático
```

Implementación en `DatabaseAdapter`:

```python
class TransactionContext:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            self.db.commit()
        else:
            self.db.rollback()
        return False
```

> Nota: en el estado del último commit, `SQLiteAdapter.execute()` ya hace auto-commit, por lo que las transacciones envuelven operaciones que de todas formas commitean individualmente. Esto es una limitación conocida de la versión commiteada.

---

## 13. Mapa Completo de Archivos (Committed State)

```
src/
├── __init__.py                        # Vacío (raíz del paquete)
│
├── orm/
│   ├── __init__.py                    # Exports públicos del ORM
│   ├── base.py                        # Clase Model con __init_subclass__
│   ├── setup.py                       # setup_model() — inicialización de modelos
│   ├── config.py                      # configure() / get_default_db()
│   ├── registry.py                    # ModelRegistry singleton
│   ├── fields.py                      # Field, PrimaryKeyField, CharField, IntegerField,
│   │                                  #   FloatField, BooleanField, DateTimeField, TextField
│   ├── field_decorators.py            # @primary_key, @char_field, @integer_field, etc.
│   ├── decorators.py                  # @model decorator
│   ├── _methods.py                    # save, delete, create_table, drop_table
│   ├── manager.py                     # ModelManager
│   ├── query.py                       # QuerySet, Q
│   ├── exceptions.py                  # ORMError, ModelError, FieldError, QueryError, DoesNotExist
│   ├── constraints.py                 # Index, CheckConstraint, UniqueConstraint
│   │
│   ├── db/
│   │   ├── __init__.py                # Exporta DatabaseAdapter, SQLiteAdapter
│   │   ├── base.py                    # DatabaseAdapter (ABC)
│   │   └── sqlite.py                  # SQLiteAdapter
│   │
│   ├── migrations/
│   │   ├── __init__.py                # Exports públicos de migraciones
│   │   ├── state.py                   # ModelState, ColumnState, IndexState, FKState, M2MTableState
│   │   ├── inspector.py               # Inspector (PRAGMA-based)
│   │   ├── differ.py                  # SchemaDiffer
│   │   ├── operations.py              # CreateTable, DropTable, AddColumn, DropColumn,
│   │   │                             #   CreateIndex, DropIndex, IrreversibleError
│   │   ├── migration.py               # Migration (ABC)
│   │   ├── migrator.py                # Migrator — apply/rollback
│   │   └── autogen.py                 # make_migration()
│   │
│   └── relations/
│       ├── __init__.py                # Exports públicos de relaciones
│       ├── fields.py                  # ForeignKey, OneToOneField, ManyToManyField
│       └── related.py                 # RelatedManager, ManyRelatedManager,
│                                     #   ManyToManyForwardManager
│
├── connection/
│   ├── __init__.py                    # Vacío (legacy)
│   └── sqlite.py                      # Database class (alternativa legacy a SQLiteAdapter)
│
├── tests/
│   ├── __init__.py
│   ├── run_tests.py                   # Script para ejecutar tests
│   ├── test_fields.py
│   ├── test_connection.py
│   ├── test_orm.py
│   ├── test_decorators.py
│   └── test_orm_advanced.py
│
├── examples/
│   ├── __init__.py
│   └── orm_example.py                 # Demo completa de los 3 enfoques
│
└── utils/
    ├── __init__.py
    └── logger.py                      # Sistema de logging
```

---

## 14. Último Commit: `7a10a27`

```
feat: add query builder module with clauses and builder pattern

Fecha: 2026-05-12 22:31:19 -0600
Autor: jose quinta
```

Este commit introdujo:
- `src/orm/query_builder/builder.py` — `QueryBuilder` con compilación SQL
- `src/orm/query_builder/clauses.py` — `Select`, `Condition`, `RawCondition`, `Where`, `Join`, `OrderBy`, `Limit`, `Offset`, `CompiledQuery`

Antes de este commit, la construcción de consultas SQL estaba dispersa en `query.py`. Con el `QueryBuilder` se centralizó la lógica de compilación, sentando las bases para futuros dialectos SQL.

### Árbol de commits

```
7a10a27 ── feat: add query builder module with clauses and builder pattern
    │
2fd1b4e ── feat: complete ORM with relations, migrations, constraints, and examples
    │
6c9642d ── feat: add decorator-based model definition and field decorators
    │
137dded ── Initial commit: Python SQLite ORM
```

---

## 15. Mockup Visual: Consulta End-to-End

```
USUARIO
   │
   │  User.objects.filter(age__gt=18, is_active=True).order_by("name DESC").limit(10).all()
   │
   v
┌─────────────────────────────────────────────────────────────────────┐
│ ModelManager.filter(age__gt=18, is_active=True)                    │
│   src/orm/manager.py:16                                            │
│   Crea QuerySet(User) y delega                                     │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           v
┌─────────────────────────────────────────────────────────────────────┐
│ QuerySet.filter(age__gt=18, is_active=True)                       │
│   src/orm/query.py:195                                            │
│                                                                   │
│   Por cada kwarg:                                                 │
│     "age__gt" → ("user.age", ">", 18)                             │
│     "is_active" → ("user.is_active", "=", True)                   │
│                                                                   │
│   _builder._where.add("user.age", ">", 18)                        │
│   _builder._where.add("user.is_active", "=", True)                │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           v
┌─────────────────────────────────────────────────────────────────────┐
│ QuerySet.order_by("name DESC")                                    │
│   _builder.order_by("name DESC")  →  OrderBy.add("name DESC")     │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           v
┌─────────────────────────────────────────────────────────────────────┐
│ QuerySet.limit(10)                                                │
│   _builder.limit(10)  →  Limit(10)                                │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           v
┌─────────────────────────────────────────────────────────────────────┐
│ QuerySet.all()     [query.py:484]                                 │
│   query, params = self._build_query()                             │
│                    → QueryBuilder.compile()                       │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           v
┌─────────────────────────────────────────────────────────────────────┐
│ QueryBuilder.compile()   [builder.py:82]                          │
│                                                                   │
│   SQL = """SELECT * FROM user                                     │
│           WHERE user.age > ? AND user.is_active = ?               │
│           ORDER BY name DESC                                      │
│           LIMIT 10"""                                             │
│                                                                   │
│   params = [18, True]                                             │
│                                                                   │
│   → CompiledQuery(sql="SELECT ...", params=[18, True])            │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           v
┌─────────────────────────────────────────────────────────────────────┐
│ SQLiteAdapter.query("SELECT * FROM user WHERE ...", [18, True])   │
│   src/orm/db/sqlite.py:59                                         │
│                                                                   │
│   1. Obtiene conexión del hilo actual (threading.local())         │
│   2. Adquiere lock                                                │
│   3. cursor.execute(sql, params)                                  │
│   4. No hace commit (es solo lectura)                             │
│   5. Libera lock                                                  │
│   6. Retorna cursor                                               │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           v
┌─────────────────────────────────────────────────────────────────────┐
│ sqlite3 (librería estándar de Python)                             │
│   /data/mi_app.db                                                 │
│                                                                   │
│   cursor.fetchall() → [                                           │
│       <sqlite3.Row: (id=2, name="Charlie", age=25, ...)>,        │
│       <sqlite3.Row: (id=5, name="Bob", age=30, ...)>,            │
│       <sqlite3.Row: (id=1, name="Alice", age=30, ...)>,          │
│   ]                                                               │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           v
┌─────────────────────────────────────────────────────────────────────┐
│ QuerySet.all() (continuación)                                     │
│   rows = cursor.fetchall()                                        │
│   results = [User(**dict(row)) for row in rows]                   │
│     → para cada fila:                                             │
│       1. Crea instancia User.__init__(**campos)                   │
│       2. init_model() asigna cada valor al atributo               │
│                                                                   │
│   Retorna [User{"id":2,"name":"Charlie",...},                     │
│            User{"id":5,"name":"Bob",...},                         │
│            User{"id":1,"name":"Alice",...}]                       │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           v
                      USUARIO RECIBE:
                      >>> [<User: {'id':2, 'name':'Charlie', ...}>,
                           <User: {'id':5, 'name':'Bob', ...}>,
                           <User: {'id':1, 'name':'Alice', ...}>]
```

---

## 16. Resumen del Flujo Completo (desde que el programa arranca)

```
1. Programa inicia
       │
2. configure(SQLiteAdapter(...))    ← establece DB global
   db.connect()
       │
3. Se definen clases de modelo:
   class User(Model): ...
       │
       └─ Python ejecuta __init_subclass__
          └─ setup_model(cls)
             ├─ descubre fields
             ├─ crea ModelManager
             ├─ asigna _db
             └─ registra en registry
       │
4. main():
   User.create_table()              ← CREATE TABLE IF NOT EXISTS ...
       │
5. User.objects.create(...)         ← INSERT OR REPLACE
   user.save()                      ← INSERT o UPDATE
       │
6. User.objects.filter(...).all()   ← SELECT con WHERE
   User.objects.get(...)            ← SELECT + LIMIT 1
       │
7. user.delete()                    ← DELETE
   User.objects.filter(...).delete()← DELETE masivo
   User.objects.filter(...).update()← UPDATE masivo
       │
8. make_migration()                 ← genera archivo de migración
   migrator.migrate()              ← aplica migraciones pendientes
       │
9. db.close()                       ← cierra conexiones
```

---

*Documento generado basado en el código del repositorio en el commit `7a10a27` (2026-05-12).*
