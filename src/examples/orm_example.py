import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.orm import (
    Model,
    model,
    primary_key,
    char_field,
    integer_field,
    boolean_field,
    PrimaryKeyField,
    CharField,
    IntegerField,
    BooleanField,
    SQLiteAdapter,
    registry,
)
from src.orm.config import configure
from src.utils.logger import setup_logger


def main():
    setup_logger(level=20)

    db = SQLiteAdapter(
        db_directory="data",
        db_name="orm_example",
        db_name_extension="db",
    )
    db.connect()

    configure(db)

    # --- Enfoque 1: Herencia clásica con Field classes ---
    class User(Model):
        _table_name = "users"

        id = PrimaryKeyField()
        name = CharField(max_length=100, null=False)
        email = CharField(max_length=255, unique=True)
        age = IntegerField(null=True)
        is_active = BooleanField(default=True)

    # --- Enfoque 2: @model con field decorators en asignación ---
    @model(table_name= "products") #type: ignore
    class Product:
        id = primary_key()
        name = char_field(max_length=200, null=False)
        price = integer_field(null=False)
        in_stock = boolean_field(default=True)

    # --- Enfoque 3: @model con field decorators sobre métodos ---
    @model(table_name="tags") #type: ignore
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

    print("Creating tables...")
    User.create_table()
    Product.create_table()
    Tag.create_table()

    print("Clearing existing data...")
    User.objects.filter().delete()
    Product.objects.filter().delete()
    Tag.objects.filter().delete()

    print("\n--- Users (herencia + Field classes) ---")
    user1 = User.objects.create(
        name="Alice", email="alice@test.com", age=30,
    )
    print(f"  Created: {user1}")

    user2 = User.objects.create(
        name="Bob", email="bob@test.com", age=25, is_active=False,
    )
    print(f"  Created: {user2}")

    print("\nAll users:")
    for u in User.objects.all():
        print(f"  {u}")

    print("\n--- Products (@model + field decorators en asignación) ---")
    product1 = Product.objects.create(
        name="Laptop", price=1000, in_stock=True,
    )
    print(f"  Created: {product1}")

    product2 = Product.objects.create(
        name="Mouse", price=25, in_stock=False,
    )
    print(f"  Created: {product2}")

    print("\nAll products:")
    for p in Product.objects.all():
        print(f"  {p}")

    print("\n--- Tags (@model + field decorators sobre métodos) ---")
    tag1 = Tag.objects.create(name="python", is_active=True)
    print(f"  Created: {tag1}")

    tag2 = Tag.objects.create(name="sqlite", is_active=True)
    print(f"  Created: {tag2}")

    tag3 = Tag.objects.create(name="deprecated", is_active=False)
    print(f"  Created: {tag3}")

    print("\nAll tags:")
    for t in Tag.objects.all():
        print(f"  {t}")

    print("\nFilter active tags:")
    for t in Tag.objects.filter(is_active=True).all():
        print(f"  {t}")

    print("\nAggregations (Users):")
    agg = User.objects.aggregate(
        total="COUNT(*)",
        avg_age="AVG(age)",
        max_age="MAX(age)",
    )
    print(f"  Total: {agg.get('total')}")
    print(f"  Avg age: {agg.get('avg_age')}")
    if agg.get("max_age"):
        print(f"  Max age: {agg.get('max_age')}")

    print("\nRegistered models:")
    for name in registry.get_all():
        print(f"  {name}")

    db.close()


if __name__ == "__main__":
    main()
