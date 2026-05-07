import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.orm import (
  Model,
  CharField,
  IntegerField,
  PrimaryKeyField,
  BooleanField,
  SQLiteAdapter,
  registry
)
from src.orm.config import configure
from src.utils.logger import setup_logger

def main():
  setup_logger(level=20)

  db = SQLiteAdapter(
    db_directory="data",
    db_name="orm_example",
    db_name_extension="db"
  )
  db.connect()

  configure(db)

  class User(Model):
    _table_name = "users"

    id = PrimaryKeyField()
    name = CharField(max_length=100, null=False)
    email = CharField(max_length=255, unique=True)
    age = IntegerField(null=True)
    is_active = BooleanField(default=True)

  print("Creating table...")
  User.create_table()

  print("Clearing existing data...")
  User.objects.filter().delete()

  print("\nCreating users:")
  user1 = User.objects.create(name="Alice", email="alice@test.com", age=30)
  print(f"  Created: {user1}")

  user2 = User.objects.create(name="Bob", email="bob@test.com", age=25, is_active=False)
  print(f"  Created: {user2}")

  user3 = User.objects.create(name="Charlie", email="charlie@test.com", age=35, is_active=True)
  print(f"  Created: {user3}")

  print("\nAll users:")
  for u in User.objects.all():
    print(f"  {u}")

  print("\nActive users:")
  for u in User.objects.filter(is_active=True).all():
    print(f"  {u}")

  print("\nAggregations:")
  agg = User.objects.aggregate(
    total="COUNT(*)",
    avg_age="AVG(age)",
    max_age="MAX(age)"
  )
  print(f"  Total users: {agg.get('total')}")
  print(f"  Average age: {agg.get('avg_age'):.1f}")
  print(f"  Max age: {agg.get('max_age')}")

  print("\nBulk update - deactivate all users under 30:")
  updated = User.objects.filter(age__lt=30).update(is_active=False)
  print(f"  Updated {updated} users")

  print("\nGet Alice by email:")
  alice = User.objects.get(email="alice@test.com")
  print(f"  Found: {alice}")

  print("\nUpdate Alice's age:")
  alice.age = 31 #type: ignore
  alice.save() #type: ignore
  alice_updated = User.objects.get(email="alice@test.com")
  print(f"  Updated: {alice_updated}")

  print(f"\nTotal users: {User.objects.count()}")

  print("\nRegistered models:")
  for name in registry.get_all(): #type: ignore
    print(f"  {name}")

  db.close()

if __name__ == "__main__":
  main()
