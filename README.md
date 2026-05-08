# Python SQLite ORM

Un ORM (Object-Relational Mapping) ligero y escalable para SQLite3, diseñado con arquitectura modular y extensible.

## 📁 Estructura del Proyecto

```
src/
├── __init__.py
├── connection/
│   ├── __init__.py
│   └── sqlite.py           # Conexión legacy (mantenida por compatibilidad)
├── examples/
│   ├── __init__.py
│   └── orm_example.py     # Ejemplos de uso del ORM
├── orm/
│   ├── __init__.py         # Exports públicos del ORM
│   ├── _methods.py         # Funciones reutilizables save/delete/create_table
│   ├── base.py             # Clase base Model
│   ├── config.py           # Configuración centralizada de BD
│   ├── decorators.py       # Decorador @model para clases sin herencia
│   ├── exceptions.py       # Excepciones personalizadas
│   ├── field_decorators.py # Decoradores de campo (primary_key, char_field, etc.)
│   ├── fields.py           # Definición de campos (CharField, IntegerField, etc.)
│   ├── manager.py          # ModelManager para operaciones de modelo
│   ├── query.py            # QuerySet para consultas avanzadas
│   ├── registry.py         # Registro central de modelos
│   ├── setup.py            # Lógica compartida setup_model()
│   ├── db/
│   │   ├── __init__.py
│   │   ├── base.py         # Interfaz abstracta DatabaseAdapter
│   │   └── sqlite.py       # Implementación SQLiteAdapter
│   ├── migrations/
│   │   ├── __init__.py
│   │   ├── migration.py    # Clase base Migration
│   │   └── migrator.py     # Sistema de migraciones
│   └── relations/
│       ├── __init__.py
│       ├── fields.py       # ForeignKey y relaciones
│       └── related.py      # RelatedManager
├── tests/
│   ├── __init__.py
│   ├── run_tests.py        # Script para ejecutar todas las pruebas
│   ├── test_fields.py      # Pruebas unitarias para campos
│   ├── test_connection.py  # Pruebas para conexión
│   ├── test_orm.py         # Pruebas para el ORM
│   ├── test_decorators.py  # Pruebas para decoradores @model y field decorators
│   └── test_orm_advanced.py# Pruebas avanzadas (filtros, agregaciones, bulk)
└── utils/
    ├── __init__.py
    └── logger.py           # Sistema de logging
```

## 🚀 Instalación y Configuración

### Prerrequisitos

- Python 3.10 o superior
- SQLite3 (incluido en Python estándar)

### Pasos de instalación

1. **Clonar el repositorio:**

```bash
git clone https://github.com/jose-quinta/orm-sqlite.git
cd orm-sqlite
```

2. **Estructura del proyecto:**

```
orm-sqlite/
├── src/
│   ├── orm/
│   ├── utils/
│   └── ...
├── main.py
└── data/                   # Directorio para la base de datos (opcional)
```

## 📖 Guía Paso a Paso

### Paso 1: Configurar la base de datos

```python
import sys
from pathlib import Path

# Asegurar que la raíz del proyecto esté en el path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.orm import SQLiteAdapter
from src.orm.config import configure
from src.utils.logger import setup_logger

# Configurar logging
setup_logger(level=20)  # INFO level

# Crear adaptador de base de datos
db = SQLiteAdapter(
    db_directory="data",      # Directorio de la BD
    db_name="mi_app",         # Nombre de la base de datos
    db_name_extension="db"    # Extensión (opcional, default: db)
)

# Conectar
db.connect()

# Configurar como base de datos por defecto (opcional pero recomendado)
configure(db)
```

### Paso 2: Definir modelos

El ORM soporta **3 enfoques** para definir modelos. Todos son equivalentes:

#### Enfoque 1: Herencia clásica con clases Field

```python
from src.orm import Model, CharField, IntegerField, PrimaryKeyField, BooleanField

class User(Model):
    _table_name = "users"  # Opcional, por defecto es el nombre de la clase en minúsculas

    id = PrimaryKeyField()
    name = CharField(max_length=100, null=False)
    email = CharField(max_length=255, unique=True)
    age = IntegerField(null=True)
    is_active = BooleanField(default=True)
```

#### Enfoque 2: Decorador @model + field decorators en asignación

```python
from src.orm import model, primary_key, char_field, integer_field, boolean_field

@model
class Product:
    id = primary_key()
    name = char_field(max_length=200, null=False)
    price = integer_field(null=False)
    in_stock = boolean_field(default=True)
```

#### Enfoque 3: Decorador @model + field decorators sobre métodos

```python
from src.orm import model, primary_key, char_field, boolean_field

@model(table_name="tags")
class Tag:
    @primary_key
    def id(self):
        ...

    @char_field(max_length=50, null=False, unique=True)
    def name(self):
        ...

    @boolean_field(default=True)
    def is_active(self):
        ...
```

### Paso 3: Crear las tablas

```python
# Crear todas las tablas necesarias
User.create_table()
Product.create_table()
Tag.create_table()
```

### Paso 4: Operaciones CRUD

#### Crear registros

```python
# Método 1: Usando el manager
user1 = User.objects.create(
    name="Alice",
    email="alice@example.com",
    age=30,
    is_active=True
)

# Método 2: Instanciando y guardando
user2 = User(
    name="Bob",
    email="bob@example.com",
    age=25
)
user2.save()
```

#### Consultar registros

```python
# Obtener todos
all_users = User.objects.all()

# Filtrar
active_users = User.objects.filter(is_active=True).all()

# Filtros avanzados
young_users = User.objects.filter(age__lt=30).all()  # age < 30
adult_users = User.objects.filter(age__gte=18).all()  # age >= 18
users_in_group = User.objects.filter(age__in=[25, 30, 35]).all()  # IN
not_equal = User.objects.filter(age__ne=30).all()  # !=
name_like = User.objects.filter(name__like="Ali%").all()  # LIKE

# Ordenar y paginar
sorted_users = User.objects.order_by("age").all()
desc_users = User.objects.order_by("age DESC").all()
first_two = User.objects.limit(2).all()
paginated = User.objects.limit(10).offset(5).all()

# Obtener uno
alice = User.objects.get(email="alice@example.com")

# Primer registro
first_user = User.objects.first()

# Verificar existencia
exists = User.objects.filter(email="test@example.com").exists()

# Contar
total = User.objects.count()
```

#### Actualizar registros

```python
# Actualización individual
user = User.objects.get(email="alice@example.com")
user.age = 31
user.save()

# Actualización masiva
updated_count = User.objects.filter(is_active=False).update(is_active=True)
```

#### Eliminar registros

```python
# Eliminación individual
user = User.objects.get(email="bob@example.com")
user.delete()

# Eliminación masiva
deleted_count = User.objects.filter(age__lt=18).delete()
```

#### Agregaciones

```python
# Obtener estadísticas
stats = User.objects.aggregate(
    total="COUNT(*)",
    avg_age="AVG(age)",
    max_age="MAX(age)",
    min_age="MIN(age)"
)

print(f"Total: {stats['total']}")
print(f"Edad promedio: {stats['avg_age']:.1f}")
```

### Paso 5: Transacciones

```python
from src.orm import SQLiteAdapter

db = SQLiteAdapter(db_directory="data", db_name="mi_app")
db.connect()

# Usar transacciones con context manager
with db.transaction():
    # Todas las operaciones aquí se confirman juntas
    user = User.objects.create(name="Test", email="test@example.com")
    Post.objects.create(title="Test Post", content="...", author_id=user.id)
    # Si hay un error, se hace rollback automático
```

## 🔧 Uso en Otro Proyecto

Para implementar este ORM en un nuevo proyecto, sigue estos pasos:

### 1. Clonar el repositorio o copiar src/

```bash
# Opción 1: Clonar el repositorio
git clone https://github.com/jose-quinta/orm-sqlite.git

# Opción 2: Copiar la carpeta src/ a tu proyecto
cp -r /ruta/a/orm-sqlite/src /nuevo/proyecto/
```

### 2. Crear el archivo principal

```python
# main.py
import sys
from pathlib import Path

# Agregar la raíz al path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.orm import (
    Model, CharField, IntegerField, PrimaryKeyField, BooleanField, SQLiteAdapter
)
from src.orm.config import configure
from src.utils.logger import setup_logger

def main():
    # Configuración
    setup_logger(level=20)

    db = SQLiteAdapter(
        db_directory="data",
        db_name="nueva_app",
        db_name_extension="db"
    )
    db.connect()
    configure(db)

    # Definir modelos
    class Product(Model):
        _table_name = "products"
        id = PrimaryKeyField()
        name = CharField(max_length=200, null=False)
        price = IntegerField(null=False)
        in_stock = BooleanField(default=True)

    # Crear tablas
    Product.create_table()

    # Usar el modelo
    Product.objects.create(name="Laptop", price=1000, in_stock=True)
    products = Product.objects.filter(in_stock=True).all()

    for p in products:
        print(f"Producto: {p.name} - Precio: {p.price}")

    db.close()

if __name__ == "__main__":
    main()
```

### 3. Estructura recomendada para nuevos proyectos

```
nuevo_proyecto/
├── main.py              # Punto de entrada
├── src/                 # ORM y utilidades (clonado del repositorio)
├── data/                # Base de datos (se crea automáticamente)
├── models/              # Tus modelos (opcional)
│   ├── __init__.py
│   ├── user.py
│   └── product.py
└── README.md
```

## ✨ Características Principales

- ✅ **Modelos declarativos**: Define tablas como clases Python
- ✅ **3 enfoques de definición**: Herencia clásica, decorador `@model` con asignación, decorador `@model` sobre métodos
- ✅ **Field decorators**: `primary_key`, `char_field`, `integer_field`, `float_field`, `boolean_field`, `datetime_field`, `text_field`
- ✅ **Tipos de campos**: CharField, IntegerField, FloatField, BooleanField, TextField, DateTimeField
- ✅ **Consultas avanzadas**: filter, exclude, order_by, limit, offset
- ✅ **Filtros especiales**: `__lt`, `__gt`, `__lte`, `__gte`, `__like`, `__in`, `__ne`, `__exact`
- ✅ **Agregaciones**: COUNT, AVG, MAX, MIN, SUM
- ✅ **Operaciones masivas**: update(), delete() en QuerySet
- ✅ **Transacciones**: Soporte con context manager
- ✅ **Configuración centralizada**: Configura la BD una vez con `configure()`
- ✅ **Thread-safe**: Conexiones seguras para múltiples hilos
- ✅ **Sistema de migraciones**: Base para evolución de esquema
- ✅ **Registro de modelos**: Registro central automático

## 🧪 Ejecutar Pruebas

```bash
# Desde la raíz del proyecto
cd /ruta/a/orm-sqlite

# Ejecutar todas las pruebas (recommendado)
python src/tests/run_tests.py

# O individualmente:
python -m unittest src.tests.test_fields -v
python -m unittest src.tests.test_connection -v
python -m unittest src.tests.test_orm -v
python -m unittest src.tests.test_decorators -v
python -m unittest src.tests.test_orm_advanced -v
```

## 📝 Ejemplo Completo

Ver el archivo `src/examples/orm_example.py` para un ejemplo completo y funcional con los 3 enfoques.

```bash
python src/examples/orm_example.py
```

## 🔮 Próximas Mejoras

- [ ] Soporte completo para ForeignKey y relaciones
- [ ] Migraciones automáticas basadas en cambios de modelos
- [ ] Soporte para otros motores (PostgreSQL, MySQL)
- [ ] Query builder más avanzado (JOINs)
- [ ] Lazy loading para relaciones
- [ ] Soporte para índices y constraints personalizados

## 📄 Licencia

Este proyecto es de uso libre para fines educativos y comerciales.
