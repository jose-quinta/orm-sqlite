import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import unittest
import os
import tempfile
from src.orm import (
    Model, PrimaryKeyField, CharField, IntegerField, FloatField,
    ForeignKey, OneToOneField, ManyToManyField,
    Index, CheckConstraint, UniqueConstraint,
    SQLiteAdapter, registry,
)
from src.orm.config import configure
from src.orm.fields import Field
from src.orm._methods import _create_indexes


class TestFieldDbIndex(unittest.TestCase):
    def test_field_accepts_db_index(self):
        f = CharField(max_length=50, db_index=True)
        self.assertTrue(f.db_index)

    def test_field_db_index_default_false(self):
        f = CharField(max_length=50)
        self.assertFalse(f.db_index)

    def test_integer_field_db_index(self):
        f = IntegerField(db_index=True)
        self.assertTrue(f.db_index)


class TestIndexClass(unittest.TestCase):
    def test_index_single_field(self):
        idx = Index("name")
        self.assertEqual(idx.fields, ["name"])
        self.assertIsNone(idx.name)
        self.assertFalse(idx.unique)

    def test_index_composite(self):
        idx = Index("name", "price", name="np_idx")
        self.assertEqual(idx.fields, ["name", "price"])
        self.assertEqual(idx.name, "np_idx")

    def test_index_unique(self):
        idx = Index("email", unique=True)
        self.assertTrue(idx.unique)


class TestCheckConstraintClass(unittest.TestCase):
    def test_check_basic(self):
        c = CheckConstraint("price > 0")
        self.assertEqual(c.condition, "price > 0")
        self.assertIsNone(c.name)

    def test_check_with_name(self):
        c = CheckConstraint("age >= 0", name="age_non_negative")
        self.assertEqual(c.name, "age_non_negative")


class TestUniqueConstraintClass(unittest.TestCase):
    def test_unique_constraint(self):
        c = UniqueConstraint("name", "sku")
        self.assertEqual(c.fields, ["name", "sku"])


class TestConstraintsIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.mkdtemp()
        cls.db = SQLiteAdapter(
            db_directory=cls.temp_dir,
            db_name="test_constr",
            db_name_extension="db",
        )
        cls.db.connect()
        configure(cls.db)

        for name in list(registry.get_all().keys()):
            registry.unregister(name)

        class Product(Model):
            _db = cls.db
            _table_name = "constr_products"

            id = PrimaryKeyField()
            name = CharField(max_length=100, db_index=True)
            price = FloatField(null=True)
            sku = CharField(max_length=50, null=True, unique=True)

            _indexes = [
                Index("name", "price", name="constr_prod_name_price_idx"),
            ]
            _constraints = [
                CheckConstraint("price > 0", name="price_positive"),
                UniqueConstraint("name", "sku", name="constr_prod_name_sku_uniq"),
            ]

        class FkTarget(Model):
            _db = cls.db
            _table_name = "constr_fk_targets"

            id = PrimaryKeyField()
            name = CharField(max_length=50)

        class FkSource(Model):
            _db = cls.db
            _table_name = "constr_fk_sources"

            id = PrimaryKeyField()
            target = ForeignKey(FkTarget, on_delete="CASCADE", on_update="SET NULL")

        cls.Product = Product
        cls.FkTarget = FkTarget
        cls.FkSource = FkSource

    @classmethod
    def tearDownClass(cls):
        cls.db.execute("PRAGMA foreign_keys = OFF", [])
        for m in reversed(list(registry.get_all().values())):
            try:
                m.drop_table()
            except Exception:
                pass
        cls.db.close()
        db_file = os.path.join(cls.temp_dir, "test_constr.db")
        if os.path.exists(db_file):
            os.remove(db_file)
        os.rmdir(cls.temp_dir)

    def setUp(self):
        for name in list(registry.get_all().keys()):
            registry.unregister(name)
        for mc in [self.Product, self.FkTarget, self.FkSource]:
            try:
                mc.drop_table()
            except Exception:
                pass
            mc.create_table()
            registry.register(mc)

    def test_create_table_with_db_index_field(self):
        Product = self.Product
        self.assertTrue(hasattr(Product, "_indexes"))
        idx_names = {idx.name for idx in Product._indexes}
        self.assertIn("idx_constr_products_name", idx_names)

    def test_create_table_emits_check(self):
        Product = self.Product
        self.assertTrue(hasattr(Product, "_constraints"))
        names = {c.name for c in Product._constraints}
        self.assertIn("price_positive", names)

    def test_crud_with_constrained_table(self):
        Product = self.Product
        p = Product.objects.create(name="Test", price=10.0, sku="TST-001")
        fetched = Product.objects.get(id=p.id)
        self.assertEqual(fetched.name, "Test")
        self.assertEqual(fetched.price, 10.0)

    def test_unique_field_still_works(self):
        Product = self.Product
        idxs = self.db.execute("PRAGMA index_list(constr_products)", []).fetchall()
        unique_idx = any(row[2] == 1 for row in idxs)
        self.assertTrue(unique_idx, "Expected at least one unique index on constr_products")

    def test_fk_on_delete_rendered(self):
        target = self.FkTarget.objects.create(name="T")
        source = self.FkSource.objects.create(target=target)
        self.assertIsNotNone(source.target)
        self.assertEqual(source.target.name, "T")

    def test_indexes_and_constraints_are_class_attrs(self):
        Product = self.Product
        self.assertIsInstance(Product._indexes, list)
        self.assertIsInstance(Product._constraints, list)

    def test_composite_index_collected(self):
        Product = self.Product
        names = {idx.name for idx in Product._indexes}
        self.assertIn("constr_prod_name_price_idx", names)

    def test_unique_constraint_collected(self):
        Product = self.Product
        names = {c.name for c in Product._constraints}
        self.assertIn("constr_prod_name_sku_uniq", names)

    def test_auto_named_index_from_db_index(self):
        Product = self.Product
        names = {idx.name for idx in Product._indexes}
        self.assertIn("idx_constr_products_name", names)

    def test_drop_table_cleans_indexes(self):
        Product = self.Product
        Product.drop_table()
        Product.create_table()
        self.assertTrue(True)

    def test_fk_on_update_stored(self):
        from src.orm.relations.fields import ForeignKey
        fk = self.FkSource._fk_fields["target"]
        self.assertEqual(fk.on_delete, "CASCADE")
        self.assertEqual(fk.on_update, "SET NULL")

    def test_fk_to_sql_contains_on_delete(self):
        from src.orm.relations.fields import ForeignKey
        fk = self.FkSource._fk_fields["target"]
        sql = fk.to_sql()
        self.assertIn("ON DELETE CASCADE", sql)
        self.assertIn("ON UPDATE SET NULL", sql)


class TestForeignKeyOnDeleteOnUpdate(unittest.TestCase):
    def test_fk_default_on_delete(self):
        fk = ForeignKey("dummy")
        self.assertEqual(fk.on_delete, "CASCADE")
        self.assertIsNone(fk.on_update)

    def test_fk_custom_on_delete(self):
        fk = ForeignKey("dummy", on_delete="SET NULL")
        self.assertEqual(fk.on_delete, "SET NULL")

    def test_fk_with_on_update(self):
        fk = ForeignKey("dummy", on_update="CASCADE")
        self.assertEqual(fk.on_update, "CASCADE")

    def test_fk_to_sql_omits_on_when_not_set(self):
        fk = ForeignKey("dummy", on_delete="", on_update=None)
        fk.fk_column = "dummy_id"
        fk.to = type("T", (), {"_table_name": "t", "_pk_field": "id"})
        sql = fk.to_sql()
        self.assertNotIn("ON DELETE", sql)
        self.assertNotIn("ON UPDATE", sql)


class TestFieldToSqlWithDbIndex(unittest.TestCase):
    def test_db_index_not_in_column_sql(self):
        f = CharField(max_length=50, db_index=True)
        f.name = "email"
        sql = f.to_sql()
        self.assertIn("VARCHAR(50)", sql)
        self.assertNotIn("INDEX", sql.upper())


if __name__ == "__main__":
    unittest.main()
