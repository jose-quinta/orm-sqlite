"""
Ejemplo completo de tienda online usando el ORM.
Demuestra: modelos, CRUD, relaciones (FK, O2O, M2M), lazy loading,
select_related, prefetch_related, Q objects, agregaciones, filtros.
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.orm import (
    Model, PrimaryKeyField, CharField, IntegerField,
    FloatField, BooleanField, DateTimeField, TextField,
    ForeignKey, OneToOneField, ManyToManyField,
    SQLiteAdapter, registry, Q,
)
from src.orm.constraints import CheckConstraint
from src.orm.config import configure


# --- ConfiguraciOn de base de datos -----------------------------------
db = SQLiteAdapter(db_directory="./data", db_name="tienda", db_name_extension="db")
db.connect()
configure(db)


# --- Modelos -----------------------------------------------------------
class Customer(Model):
    _db = db
    _table_name = "customers"

    id = PrimaryKeyField()
    name = CharField(max_length=100, null=False)
    email = CharField(max_length=200, unique=True, null=False, db_index=True)
    loyalty_points = IntegerField(default=0)
    is_active = BooleanField(default=True)
    joined_at = DateTimeField(null=True)


class CustomerProfile(Model):
    _db = db
    _table_name = "customer_profiles"

    id = PrimaryKeyField()
    phone = CharField(max_length=20, null=True)
    address = TextField(null=True)
    customer = OneToOneField(Customer, related_name="profile")


class Category(Model):
    _db = db
    _table_name = "categories"

    id = PrimaryKeyField()
    name = CharField(max_length=100, null=False)
    description = TextField(null=True)


class Product(Model):
    _db = db
    _table_name = "products"

    id = PrimaryKeyField()
    name = CharField(max_length=200, null=False)
    price = FloatField(null=False)
    stock = IntegerField(default=0)
    categories = ManyToManyField(Category, related_name="products")

    _constraints = [
        CheckConstraint("price > 0", name="price_positive"),
    ]


class Order(Model):
    _db = db
    _table_name = "orders"

    id = PrimaryKeyField()
    order_date = DateTimeField(null=True)
    shipped = BooleanField(default=False)
    customer = ForeignKey(Customer, related_name="orders")


class OrderItem(Model):
    _db = db
    _table_name = "order_items"

    id = PrimaryKeyField()
    quantity = IntegerField(null=False)
    unit_price = FloatField(null=False)
    order = ForeignKey(Order, related_name="items")
    product = ForeignKey(Product, related_name="order_items")


# --- Preparar tablas (limpiar datos de ejecuciones anteriores) --------
db.execute("PRAGMA foreign_keys = OFF", [])
for m in reversed(list(registry.get_all().values())):
    try:
        m.drop_table()
    except Exception:
        pass
for m in registry.get_all().values():
    try:
        m.create_table()
    except Exception:
        pass
db.execute("PRAGMA foreign_keys = ON", [])

for model in [Customer, CustomerProfile, Category, Product, Order, OrderItem]:
    model.create_table()

print("=== TIENDA ONLINE - EJEMPLO COMPLETO ORM ===")
print()


# =======================================================================
# 1. CREACION (CREATE)
# =======================================================================
print("--- 1. CREACION ---")

alice = Customer.objects.create(name="Alice", email="alice@mail.com", loyalty_points=100)
bob = Customer.objects.create(name="Bob", email="bob@mail.com", loyalty_points=50)
charlie = Customer.objects.create(name="Charlie", email="charlie@mail.com", loyalty_points=200)

CustomerProfile.objects.create(phone="555-0101", address="Calle 1", customer=alice)
CustomerProfile.objects.create(phone="555-0202", address="Calle 2", customer=bob)

cat_electronics = Category.objects.create(name="ElectrOnica", description="Gadgets y dispositivos")
cat_books = Category.objects.create(name="Libros", description="Libros fisicos y digitales")
cat_clothing = Category.objects.create(name="Ropa", description="Indumentaria")

laptop = Product.objects.create(name="Laptop Pro", price=1500.00, stock=10)
phone = Product.objects.create(name="SmartPhone X", price=800.00, stock=25)
book = Product.objects.create(name="Python 101", price=45.00, stock=100)
tshirt = Product.objects.create(name="Camiseta ORM", price=25.00, stock=50)

laptop.categories.add(cat_electronics)
phone.categories.add(cat_electronics)
book.categories.add(cat_books)
tshirt.categories.add(cat_clothing)

order1 = Order.objects.create(customer=alice)
OrderItem.objects.create(order=order1, product=laptop, quantity=1, unit_price=1500.00)
OrderItem.objects.create(order=order1, product=book, quantity=2, unit_price=45.00)

order2 = Order.objects.create(customer=bob)
OrderItem.objects.create(order=order2, product=phone, quantity=1, unit_price=800.00)

order3 = Order.objects.create(customer=alice)
OrderItem.objects.create(order=order3, product=tshirt, quantity=3, unit_price=25.00)

print(f"Clientes: {Customer.objects.count()}")
print(f"Productos: {Product.objects.count()}")
print(f"Categorias: {Category.objects.count()}")
print(f"Ordenes: {Order.objects.count()}")
print(f"Items: {OrderItem.objects.count()}")
print()


# =======================================================================
# 2. LAZY LOADING - FK FORWARD
# =======================================================================
print("--- 2. LAZY LOADING: FK FORWARD ---")

order = Order.objects.get(id=order1.id)
# Acceder a la relaciOn dispara la query (lazy)
print(f"Orden #{order.id} -> Cliente: {order.customer.name}")
print(f"  (cacheado: {'_customer_cached' in order.__dict__})")
# Segundo acceso usa cache -- 0 queries
print(f"  nombre otra vez: {order.customer.name} (desde cache)")
print()


# =======================================================================
# 3. LAZY LOADING - FK REVERSE (cache + invalidaciOn)
# =======================================================================
print("--- 3. LAZY LOADING: FK REVERSE ---")

alice = Customer.objects.get(id=alice.id)
orders = alice.orders.all()
print(f"Ordenes de Alice: {len(orders)} (cacheado)")
orders_again = alice.orders.all()
print(f"  segunda llamada: {len(orders_again)} (misma lista en cache)")

# Crear una nueva orden invalida el cache
new_order = alice.orders.create()
OrderItem.objects.create(order=new_order, product=laptop, quantity=1, unit_price=1500.00)
new_count = len(alice.orders.all())
print(f"  después de crear: {new_count} Ordenes (cache refrescado)")
print()


# =======================================================================
# 4. LAZY LOADING - O2O REVERSE
# =======================================================================
print("--- 4. LAZY LOADING: O2O REVERSE ---")

alice = Customer.objects.get(id=alice.id)
profile = alice.profile
print(f"Perfil de Alice: {profile.phone}, {profile.address} (lazy, cacheado)")
# Segundo acceso no hace query
print(f"  desde cache: {alice.profile.phone}")
print()


# =======================================================================
# 5. M2M FORWARD
# =======================================================================
print("--- 5. M2M FORWARD ---")

laptop = Product.objects.get(id=laptop.id)
cats = laptop.categories.all()
print(f"Categorias de '{laptop.name}': {[c.name for c in cats]}")
laptop.categories.add(cat_clothing)
print(f"  después de añadir Ropa: {[c.name for c in laptop.categories.all()]}")
laptop.categories.remove(cat_clothing)
print(f"  después de quitar Ropa: {[c.name for c in laptop.categories.all()]}")
print()


# =======================================================================
# 6. SELECT_RELATED (JOIN eager loading)
# =======================================================================
print("--- 6. SELECT_RELATED ---")

orders = Order.objects.select_related("customer").all()
for o in orders:
    print(f"  Orden #{o.id}: {o.customer.name} (1 query total con JOIN)")
print()


# =======================================================================
# 7. PREFETCH_RELATED (batch loading)
# =======================================================================
print("--- 7. PREFETCH_RELATED ---")

# Reverse FK en batch (2 queries total)
customers = Customer.objects.prefetch_related("orders", "profile").all()
for c in customers:
    order_count = len(c.orders.all())
    phone = c.profile.phone if c.profile else "N/A"
    print(f"  {c.name}: {order_count} Ordenes, tel: {phone}")

# M2M forward en batch (3 queries total)
products = Product.objects.prefetch_related("categories").all()
for p in products:
    cat_names = [cat.name for cat in p.categories.all()]
    print(f"  '{p.name}': categorias = {cat_names}")
print()


# =======================================================================
# 8. FILTROS CON TRAVERSAL DE RELACIONES (JOIN automático)
# =======================================================================
print("--- 8. FILTROS POR RELACIONES ---")

# Filtrar Ordenes por nombre de cliente (usa LEFT JOIN)
orders_alice = Order.objects.filter(customer__name="Alice").all()
print(f"Ordenes de Alice: {len(orders_alice)}")

# Filtrar con operadores
big_spenders = Order.objects.filter(customer__loyalty_points__gte=100).all()
print(f"Ordenes de clientes con >=100 puntos: {len(big_spenders)}")

# Filtrar productos por categoria
electronics = Product.objects.filter(categories__name="ElectrOnica").all()
print(f"Productos en ElectrOnica: {[p.name for p in electronics]}")

# Excluir por relaciOn
not_alice = Order.objects.exclude(customer__name="Alice").all()
print(f"Ordenes que NO son de Alice: {len(not_alice)}")
print()


# =======================================================================
# 9. Q OBJECTS (condiciones complejas AND/OR/NOT)
# =======================================================================
print("--- 9. Q OBJECTS ---")

# OR: productos baratos O con stock bajo
cheap_or_low = Product.objects.filter(
    Q(price__lt=50) | Q(stock__lt=15)
).all()
print(f"Precio<50 o stock<15: {[p.name for p in cheap_or_low]}")

# NOT: excluir categoria
not_electronics = Product.objects.exclude(
    Q(categories__name="ElectrOnica")
).all()
print(f"NO ElectrOnica: {[p.name for p in not_electronics]}")

# Combinado
specific = Product.objects.filter(
    Q(price__gte=100) & (Q(stock__gte=10) | Q(name__like="%Phone%"))
).all()
print(f"(Precio>=100) AND (stock>=10 OR nombre='%Phone%'): {[p.name for p in specific]}")
print()


# =======================================================================
# 10. AGREGACIONES
# =======================================================================
print("--- 10. AGREGACIONES ---")

agg = Product.objects.aggregate(
    avg_price="AVG(price)",
    max_price="MAX(price)",
    min_price="MIN(price)",
    total_stock="SUM(stock)",
)
print(f"Precio promedio: ${agg['avg_price']:.2f}")
print(f"Precio más alto: ${agg['max_price']:.2f}")
print(f"Stock total: {agg['total_stock']}")

# Con filtro por relaciOn
electronics_agg = Product.objects.filter(
    categories__name="ElectrOnica"
).aggregate(avg_price="AVG(price)")
print(f"Precio promedio en ElectrOnica: ${electronics_agg['avg_price']:.2f}")
print()


# =======================================================================
# 11. BULK UPDATE / DELETE con filtros por relaciOn
# =======================================================================
print("--- 11. BULK UPDATE / DELETE ---")

# Update: marcar como enviadas todas las Ordenes de Alice
updated = Order.objects.filter(customer__name="Alice").update(shipped=True)
print(f"Ordenes de Alice marcadas como enviadas: {updated}")

# Delete: eliminar items de Ordenes ya enviadas
deleted = OrderItem.objects.filter(order__shipped=True).delete()
print(f"Items de Ordenes enviadas eliminados: {deleted}")
print()


# =======================================================================
# 12. FIRST, EXISTS, GET_OR_CREATE
# =======================================================================
print("--- 12. MÉTODOS ÚTILES ---")

first_customer = Customer.objects.first()
print(f"Primer cliente: {first_customer.name}")

exists = Customer.objects.filter(name="Alice").exists()
print(f"¿Alice existe? {exists}")

customer, created = Customer.objects.get_or_create(
    defaults={"loyalty_points": 0},
    email="diana@mail.com",
    name="Diana",
)
print(f"Cliente Diana: {'creado' if created else 'existente'} (puntos: {customer.loyalty_points})")
print()


# =======================================================================
# 13. ORDER_BY / LIMIT / OFFSET
# =======================================================================
print("--- 13. PAGINACION Y ORDEN ---")

top_products = Product.objects.order_by("-price").limit(2).all()
print(f"Productos más caros (top 2): {[p.name for p in top_products]}")

page = Product.objects.order_by("name").limit(2).offset(1).all()
print(f"Página 2 (2 items): {[p.name for p in page]}")
print()


# =======================================================================
# 14. SELECT (columnas especificas)
# =======================================================================
print("--- 14. SELECT ESPECiFICO ---")

names = Product.objects.select("name", "price").all()
for n in names:
    print(f"  {n.name}: ${n.price}")
print()


# =======================================================================
# 15. CONSTRAINTS e INDEXES
# =======================================================================
print("--- 15. CONSTRAINTS E INDEXES ---")

# CheckConstraint: precio debe ser > 0
try:
    Product.objects.create(name="Prod Invalido", price=-10.00, stock=1)
    print("  ERROR: Deberia haber lanzado excepcion por precio negativo")
except Exception as e:
    print(f"  CheckConstraint 'price > 0' funciona: {e}")

# db_index=True en email (verificado via EXPLAIN QUERY PLAN)
result = db.execute(
    "EXPLAIN QUERY PLAN SELECT * FROM customers WHERE email = ?",
    ["alice@mail.com"],
)
row = result.fetchone()
if row and "SEARCH" in str(row):
    print(f"  Index en email usado por el planner: {row}")
else:
    print(f"  Consulta por email ejecutada (resultado: {row})")

print()

# --- Limpieza ----------------------------------------------------------
'''db.execute("PRAGMA foreign_keys = OFF", [])
for m in reversed(list(registry.get_all().values())):
    m.drop_table()
db.close()

import os
db_path = os.path.join("data", "tienda.db")
if os.path.exists(db_path):
    os.remove(db_path)'''

print("=== FIN DEL EJEMPLO ===")
