import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import unittest
import os
import tempfile
from src.orm import (
    Model,
    PrimaryKeyField,
    CharField,
    IntegerField,
    FloatField,
    BooleanField,
    SQLiteAdapter,
    registry,
)
from src.orm.config import configure
from src.orm.exceptions import DoesNotExist


class TestAdvancedQueries(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.mkdtemp()
        cls.db = SQLiteAdapter(
            db_directory=cls.temp_dir,
            db_name="test_advanced",
            db_name_extension="db",
        )
        cls.db.connect()
        configure(cls.db)

        class User(Model):
            _db = cls.db
            _table_name = "users"

            id = PrimaryKeyField()
            name = CharField(max_length=100, null=False)
            email = CharField(max_length=255, unique=True)
            age = IntegerField(null=True)
            salary = FloatField(null=True)
            is_active = BooleanField(default=True)

        cls.User = User
        cls.User.create_table()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()
        db_file = os.path.join(cls.temp_dir, "test_advanced.db")
        if os.path.exists(db_file):
            os.remove(db_file)
        os.rmdir(cls.temp_dir)

    def setUp(self):
        for u in self.User.objects.all():
            u.delete()
        self._seed()

    def _seed(self):
        users_data = [
            ("Alice", "alice@test.com", 25, 50000.0, True),
            ("Bob", "bob@test.com", 30, 60000.0, True),
            ("Charlie", "charlie@test.com", 35, 70000.0, False),
            ("Diana", "diana@test.com", 28, 55000.0, True),
            ("Eve", "eve@test.com", 22, 45000.0, False),
        ]
        for name, email, age, salary, active in users_data:
            self.User.objects.create(
                name=name,
                email=email,
                age=age,
                salary=salary,
                is_active=active,
            )

    # --- Filter operators ---

    def test_filter_gt(self):
        results = self.User.objects.filter(age__gt=30).all()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].name, "Charlie")

    def test_filter_gte(self):
        results = self.User.objects.filter(age__gte=30).all()
        self.assertEqual(len(results), 2)

    def test_filter_lt(self):
        results = self.User.objects.filter(age__lt=25).all()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].name, "Eve")

    def test_filter_lte(self):
        results = self.User.objects.filter(age__lte=25).all()
        self.assertEqual(len(results), 2)

    def test_filter_ne(self):
        results = self.User.objects.filter(age__ne=25).all()
        self.assertEqual(len(results), 4)

    def test_filter_like(self):
        results = self.User.objects.filter(name__like="Ali%").all()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].name, "Alice")

    def test_filter_in(self):
        results = self.User.objects.filter(age__in=[25, 30]).all()
        self.assertEqual(len(results), 2)

        results = self.User.objects.filter(age__in=[25]).all()
        self.assertEqual(len(results), 1)

    def test_filter_chained(self):
        results = (
            self.User.objects
            .filter(is_active=True)
            .filter(age__gte=28)
            .all()
        )
        self.assertEqual(len(results), 2)

    # --- Exclude ---

    def test_exclude(self):
        results = self.User.objects.exclude(is_active=False).all()
        for u in results:
            self.assertTrue(u.is_active)
        self.assertEqual(len(results), 3)

    def test_exclude_with_operator(self):
        results = self.User.objects.exclude(age__lt=28).all()
        for u in results:
            self.assertGreaterEqual(u.age, 28)
        self.assertEqual(len(results), 3)

    # --- Order by ---

    def test_order_by_asc(self):
        results = self.User.objects.order_by("age").all()
        ages = [u.age for u in results]
        self.assertEqual(ages, sorted(ages))

    def test_order_by_desc(self):
        results = self.User.objects.order_by("age DESC").all()
        ages = [u.age for u in results]
        self.assertEqual(ages, sorted(ages, reverse=True))

    # --- Limit / Offset ---

    def test_limit(self):
        results = self.User.objects.limit(2).all()
        self.assertEqual(len(results), 2)

    def test_limit_with_offset(self):
        results = self.User.objects.order_by("age").limit(2).offset(1).all()
        self.assertEqual(len(results), 2)
        ages = [u.age for u in results]
        self.assertGreater(ages[0], 22)

    # --- First / Exists / Count ---

    def test_first(self):
        first = self.User.objects.first()
        self.assertIsNotNone(first)

    def test_first_empty(self):
        for u in self.User.objects.all():
            u.delete()
        first = self.User.objects.first()
        self.assertIsNone(first)

    def test_exists_true(self):
        exists = self.User.objects.filter(name="Alice").exists()
        self.assertTrue(exists)

    def test_exists_false(self):
        exists = self.User.objects.filter(name="Zoe").exists()
        self.assertFalse(exists)

    def test_count(self):
        count = self.User.objects.count()
        self.assertEqual(count, 5)

    # --- Get / Get or create ---

    def test_get_found(self):
        user = self.User.objects.get(email="alice@test.com")
        self.assertEqual(user.name, "Alice")

    def test_get_not_found(self):
        with self.assertRaises(DoesNotExist):
            self.User.objects.get(email="nonexistent@test.com")

    def test_get_or_create_existing(self):
        user, created = self.User.objects.get_or_create(
            defaults={"age": 30}, email="alice@test.com"
        )
        self.assertFalse(created)
        self.assertEqual(user.name, "Alice")

    def test_get_or_create_new(self):
        user, created = self.User.objects.get_or_create(
            defaults={"name": "Frank", "age": 40},
            email="frank@test.com",
        )
        self.assertTrue(created)
        self.assertEqual(user.name, "Frank")

        self.User.objects.get(email="frank@test.com").delete()

    # --- Bulk operations ---

    def test_bulk_update(self):
        updated = self.User.objects.filter(is_active=False).update(is_active=True)
        self.assertEqual(updated, 2)

        active_count = self.User.objects.filter(is_active=True).count()
        self.assertEqual(active_count, 5)

    def test_bulk_delete(self):
        deleted = self.User.objects.filter(is_active=False).delete()
        self.assertEqual(deleted, 2)
        self.assertEqual(self.User.objects.count(), 3)

    # --- Aggregate ---

    def test_aggregate_count(self):
        agg = self.User.objects.aggregate(total="COUNT(*)")
        self.assertEqual(agg["total"], 5)

    def test_aggregate_avg(self):
        agg = self.User.objects.aggregate(avg_age="AVG(age)")
        self.assertGreater(agg["avg_age"], 0)

    def test_aggregate_min_max(self):
        agg = self.User.objects.aggregate(
            min_age="MIN(age)", max_age="MAX(age)"
        )
        self.assertEqual(agg["min_age"], 22)
        self.assertEqual(agg["max_age"], 35)

    # --- Create table / Drop table ---

    def test_drop_and_recreate(self):
        self.User.drop_table()
        self.User.create_table()
        count = self.User.objects.count()
        self.assertEqual(count, 0)

        u = self.User.objects.create(
            name="New", email="new@test.com", age=1
        )
        self.assertIsNotNone(u.id)
        u.delete()


if __name__ == "__main__":
    unittest.main()
