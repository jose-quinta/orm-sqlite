# ORM-SQLite

**ORM ligero, modular y extensible con soporte multi-base de datos, sistema de migraciones y dialectos.**

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

---

## Características Principales

- **Modelos declarativos** — 3 enfoques: herencia clásica, `@model` con asignación, `@model` sobre métodos
- **Multi-base de datos simultánea** — Varias conexiones con nombres, conmutables por modelo
- **Configuración por URL** — `sqlite:///ruta`, `postgresql://user:pass@host/db`, `mysql://user:pass@host/db`
- **Sistema de dialectos** — SQLite, PostgreSQL y MySQL con generación de SQL específica
- **Consultas avanzadas** — filter, exclude, order_by, limit, offset, Q expressions
- **Filtros especiales** — `__lt`, `__gt`, `__lte`, `__gte`, `__like`, `__in`, `__ne`, `__exact`
- **Agregaciones** — COUNT, AVG, MAX, MIN, SUM
- **Relaciones** — ForeignKey, OneToOneField, ManyToManyField con lazy loading
- **Transacciones** — Context manager, savepoints, nested transactions
- **Sistema de migraciones** — Creación, detección de cambios, autogeneración, rollback
- **Constraints** — `Index`, `UniqueConstraint`, `CheckConstraint`, foreign key ON DELETE/UPDATE
- **Field decorators** — `primary_key`, `char_field`, `integer_field`, `float_field`, `boolean_field`, `datetime_field`, `text_field`
- **Configuración centralizada** — `configure()`, `configure_from_url()`, bases de datos nombradas
- **Thread-safe** — Conexiones seguras para múltiples hilos

---

## Instalación

```bash
git clone https://github.com/jose-quinta/orm-sqlite.git
cd orm-sqlite
```

> **Requiere:** Python 3.10+ · Para PostgreSQL: `psycopg2` · Para MySQL: `pymysql`

---

## Guía Rápida

### 1. Configurar la base de datos

```python
from src.orm import SQLiteAdapter
from src.orm.config import configure

db = SQLiteAdapter(db_directory="data", db_name="mi_app")
db.connect()
configure(db)
```

### 2. Definir modelos

```python
from src.orm import (
    Model, PrimaryKeyField, CharField, IntegerField,
    ForeignKey, Index,
)

class User(Model):
    _table_name = "users"
    id = PrimaryKeyField()
    name = CharField(max_length=100, null=False)
    email = CharField(max_length=255, unique=True)
    age = IntegerField(null=True)

class Post(Model):
    _table_name = "posts"
    id = PrimaryKeyField()
    title = CharField(max_length=200)
    author = ForeignKey(User, on_delete="CASCADE")

    _indexes = [Index("title")]
```

### 3. Crear tablas y operaciones CRUD

```python
User.create_table()
Post.create_table()

# Create
user = User.objects.create(name="Alice", email="alice@example.com", age=30)

# Read
users = User.objects.filter(age__gte=18).order_by("name").all()
alice = User.objects.get(email="alice@example.com")

# Update
alice.age = 31
alice.save()

# Delete
alice.delete()
```

---

## Configuración por URL

Puedes configurar cualquier base de datos usando una URL de conexión:

```python
from src.orm.db.registry import create_adapter

# SQLite archivo
db = create_adapter("sqlite:///data/mi_app.db")

# SQLite en memoria
db = create_adapter("sqlite:///:memory:")

# PostgreSQL
db = create_adapter("postgresql://user:pass@localhost:5432/mydb")

# MySQL con charset
db = create_adapter("mysql://root:secret@localhost:3306/myshop?charset=utf8mb4")
```

O usando variable de entorno:

```python
import os
os.environ["DATABASE_URL"] = "postgresql://user:pass@localhost:5432/mydb"

from src.orm.db.registry import create_adapter_from_env
db = create_adapter_from_env()
```

Configuración en un solo paso:

```python
from src.orm.config import configure_from_url

configure_from_url("sqlite:///data/mi_app.db")
```

---

## Múltiples Bases de Datos

Puedes trabajar con varias bases de datos simultáneamente:

```python
from src.orm.config import configure_from_url, register_db, get_db

# Registrar varias conexiones con nombre
configure_from_url("sqlite:///data/principal.db", name="default")
configure_from_url("sqlite:///data/logs.db", name="logs")

# Recuperar una conexión por nombre
logs_db = get_db("logs")

# Asignar una base de datos específica a un modelo
class LogEntry(Model):
    _db = logs_db  # Este modelo usa la BD "logs"
    _table_name = "logs"
    id = PrimaryKeyField()
    message = CharField(max_length=500)

# Listar todas las conexiones activas
from src.orm.config import get_all_dbs
print(get_all_dbs())  # {"default": <...>, "logs": <...>}
```

---

## Migraciones

El sistema de migraciones detecta cambios entre tus modelos y la base de datos, y genera código Python para aplicar/esquematizar esos cambios.

### Crear una migración

```python
from src.orm.migrations.autogen import make_migration

# Compara modelos registrados vs DB y genera archivo de migración
archivo = make_migration(db, migrations_dir="migrations", message="Add users table")
print(f"Migración creada: {archivo}")
```

### Aplicar migraciones

```python
from src.orm.migrations import Migrator

migrator = Migrator(db, migrations_dir="migrations")
migrator.load_migrations()
migrator.migrate()           # Aplica todas las pendientes
migrator.rollback("002")     # Revierte hasta la versión 002
```

### Operaciones de migración soportadas

- `CreateTable`, `DropTable`
- `AddColumn`, `DropColumn`
- `CreateIndex`, `DropIndex`

El SQL generado se adapta automáticamente al dialecto configurado (SQLite usa `PRAGMA`, PostgreSQL usa `information_schema`, etc.).

---

## Relaciones

### ForeignKey

```python
class Post(Model):
    author = ForeignKey(User, on_delete="CASCADE", on_update="SET NULL")

# Acceso forward (lazy loading)
post = Post.objects.get(id=1)
author_name = post.author.name  # Carga automática

# Acceso reverse
posts = User.objects.get(id=1).posts.all()

# Prefetch (una sola consulta adicional)
from src.orm.query import Prefetch
users = User.objects.prefetch(Prefetch("posts")).all()
```

### OneToOne

```python
class Profile(Model):
    user = OneToOneField(User)
    bio = TextField()

# Acceso forward
profile = Profile.objects.get(id=1)
user = profile.user

# Acceso reverse
profile = User.objects.get(id=1).profile
```

### ManyToMany

```python
class Project(Model):
    members = ManyToManyField(User)

# Agregar relación
project = Project.objects.get(id=1)
project.members.add(user)

# Consultar relacionados
members = project.members.all()

# Eliminar relación
project.members.remove(user)
project.members.clear()
```

---

## Constraints

```python
from src.orm import (
    Index, UniqueConstraint, CheckConstraint,
    ForeignKey,
)

class Product(Model):
    _table_name = "products"
    id = PrimaryKeyField()
    sku = CharField(max_length=50)
    price = IntegerField(null=False)
    category = CharField(max_length=50)

    _indexes = [
        Index("sku"),                             # Índice simple
        Index("category", "price", unique=True),  # Índice compuesto único
    ]
    _constraints = [
        UniqueConstraint("sku"),                              # UNIQUE
        CheckConstraint("price > 0", name="positive_price"),  # CHECK
    ]
```

---

## Field Decorators

Tres formas equivalentes de definir modelos:

```python
# 1. Clásica con herencia
class User(Model):
    id = PrimaryKeyField()
    name = CharField(max_length=100)

# 2. Decorador @model con asignación
@model
class Product:
    id = primary_key()
    name = char_field(max_length=200)

# 3. Decorador @model sobre métodos
@model(table_name="tags")
class Tag:
    @primary_key
    def id(self): ...
    @char_field(max_length=50, unique=True)
    def name(self): ...
```

---

## Transacciones

```python
# Transacción simple
with db.transaction():
    user = User.objects.create(name="Alice")
    Log.objects.create(action="created_user")

# Transacción con rollback automático
try:
    with db.transaction():
        User.objects.create(name="Bob")
        raise ValueError("algo falló")
except ValueError:
    pass  # La transacción se revierte automáticamente

# Savepoints (anidados)
with db.transaction():
    User.objects.create(name="Outer")
    with db.nested_transaction():
        User.objects.create(name="Inner")
        # Si hay error aquí, solo revierte el savepoint
```

---

## Dialectos Soportados

| Dialecto  | Esquema URL                    | Placeholder | Auto Increment | Upsert                  |
|-----------|--------------------------------|-------------|----------------|-------------------------|
| SQLite    | `sqlite:///ruta.db`            | `?`         | `AUTOINCREMENT` | `INSERT OR REPLACE`    |
| PostgreSQL| `postgresql://user:pass@host/db` | `%s`      | `SERIAL`       | `ON CONFLICT DO UPDATE`|
| MySQL     | `mysql://user:pass@host/db`      | `%s`      | `AUTO_INCREMENT`| `REPLACE INTO`         |

Cada dialecto implementa variaciones en:

- **CREATE TABLE** — Ajusta sintaxis de `IF NOT EXISTS` según soporte del motor
- **CREATE / DROP INDEX** — Sintaxis específica (MySQL no soporta `IF NOT EXISTS` en índices)
- **Introspection** — SQLite usa `PRAGMA`, PostgreSQL `information_schema`, MySQL `SHOW` / `information_schema`
- **Placeholders** — `?` para SQLite, `%s` para PostgreSQL/MySQL
- **Upsert** — Cada motor usa su mecanismo nativo

---

## Arquitectura del Proyecto

```
src/
├── orm/
│   ├── __init__.py           # Exports públicos
│   ├── base.py               # Clase base Model
│   ├── _methods.py           # save/delete/create_table/drop_table (dialect-aware)
│   ├── config.py             # Configuración multi-base de datos
│   ├── fields.py             # Definición de campos
│   ├── field_decorators.py   # Decoradores de campo
│   ├── decorators.py         # Decorador @model
│   ├── manager.py            # ModelManager
│   ├── query.py              # QuerySet, Q, Prefetch
│   ├── registry.py           # Registro de modelos
│   ├── setup.py              # setup_model()
│   ├── exceptions.py         # Excepciones personalizadas
│   ├── constraints.py        # Index, UniqueConstraint, CheckConstraint
│   ├── db/
│   │   ├── base.py           # DatabaseAdapter abstracto
│   │   ├── dialect.py        # Dialect base + SQLite, PostgreSQL, MySQL
│   │   ├── sqlite.py         # Implementación SQLiteAdapter
│   │   ├── postgresql.py     # Implementación PostgreSQLAdapter
│   │   ├── mysql.py          # Implementación MySQLAdapter
│   │   ├── registry.py       # create_adapter(), create_adapter_from_env()
│   │   └── url_parser.py     # parse_database_url()
│   ├── migrations/
│   │   ├── __init__.py
│   │   ├── migration.py      # Clase base Migration
│   │   ├── migrator.py       # Aplicar/revocar migraciones
│   │   ├── autogen.py        # Autogeneración de migraciones
│   │   ├── inspector.py      # Introspectores de esquema (dialect-aware)
│   │   ├── operations.py     # CreateTable, AddColumn, etc.
│   │   ├── differ.py         # Comparador ModelState vs DB
│   │   └── state.py          # ModelState, ColumnState, etc.
│   └── relations/
│       ├── fields.py         # ForeignKey, OneToOneField, ManyToManyField
│       └── related.py        # RelatedManager, ManyRelatedManager
├── tests/
│   ├── test_orm.py
│   ├── test_orm_advanced.py
│   ├── test_orm_relations.py
│   ├── test_adapters.py
│   ├── test_migrations.py
│   ├── test_constraints.py
│   ├── test_decorators.py
│   ├── test_fields.py
│   ├── test_connection.py
│   ├── test_lazy_loading.py
│   ├── test_query_builder.py
│   └── test_query_q.py
└── utils/
    └── logger.py
```

---

## Ejecutar Pruebas

```bash
# Todas las pruebas
python -m unittest discover -s src.tests -v

# Por módulo
python -m unittest src.tests.test_orm -v
python -m unittest src.tests.test_migrations -v
python -m unittest src.tests.test_adapters -v
```

---

## Mejoras Futuras

- [ ] **Pool de conexiones** — Pool genérico para reutilización eficiente de conexiones
- [ ] **Async support** — Versión asíncrona con `asyncio` / `aiohttp`
- [ ] **Query builder con JOINs explícitos** — `Model.objects.join(OtherModel).filter(...)`
- [ ] **Logger de queries** — Logging de todas las consultas ejecutadas con tiempo de ejecución
- [ ] **Validación de esquema completo** — Validar todas las tablas, tipos y constraints antes de operar
- [ ] **CLI interactivo** — Comando `orm migrate`, `orm inspect`, `orm shell`
- [ ] **Seeders / Fixtures** — Carga de datos iniciales desde JSON/YAML
- [ ] **Soft delete** — Eliminación lógica con campo `deleted_at`
- [ ] **Auditoría automática** — Campos `created_at` / `updated_at` automáticos
- [ ] **Cache de consultas** — Caché en memoria con invalidación automática
- [ ] **Soporte para `NOT NULL` en `compile_upsert`** — Manejo de defaults para columnas no anulables

---

## Licencia

MIT — Libre para uso educativo y comercial.
