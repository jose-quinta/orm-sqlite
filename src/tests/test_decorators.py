import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import unittest
import os
import tempfile
from src.orm import (
    Model,
    model,
    primary_key,
    char_field,
    integer_field,
    float_field,
    boolean_field,
    text_field,
    datetime_field,
    PrimaryKeyField,
    CharField,
    IntegerField,
    Field,
    SQLiteAdapter,
)
from src.orm.config import configure
from src.orm.fields import PrimaryKeyField as PKField
from src.orm.registry import registry


class TestFieldDecorators(unittest.TestCase):
    def test_primary_key_assignment(self):
        f = primary_key()
        self.assertIsInstance(f, PrimaryKeyField)

    def test_primary_key_bare_decorator(self):
        class Fake:
            @primary_key
            def id(self):
                ...

        f = Fake.__dict__["id"]
        self.assertIsInstance(f, PrimaryKeyField)

    def test_primary_key_parens_decorator(self):
        class Fake:
            @primary_key()
            def id(self):
                ...

        f = Fake.__dict__["id"]
        self.assertIsInstance(f, PrimaryKeyField)

    def test_char_field_assignment(self):
        f = char_field(max_length=100, null=False)
        self.assertIsInstance(f, CharField)
        self.assertEqual(f.max_length, 100)
        self.assertFalse(f.null)

    def test_char_field_decorator_with_kwargs(self):
        class Fake:
            @char_field(max_length=50, null=False, unique=True)
            def name(self):
                ...

        f = Fake.__dict__["name"]
        self.assertIsInstance(f, CharField)
        self.assertEqual(f.max_length, 50)

    def test_char_field_default_max_length(self):
        f = char_field()
        self.assertEqual(f.max_length, 255)

    def test_integer_field(self):
        f = integer_field(null=True)
        self.assertIsInstance(f, IntegerField)
        self.assertTrue(f.null)

    def test_float_field(self):
        f = float_field()
        self.assertIsInstance(f, Field)

    def test_boolean_field(self):
        f = boolean_field(default=False)
        self.assertIsInstance(f, Field)
        self.assertFalse(f.default)

    def test_text_field(self):
        f = text_field()
        self.assertIsInstance(f, Field)

    def test_datetime_field(self):
        f = datetime_field(auto_now=True)
        self.assertTrue(f.auto_now)

    def test_field_call_returns_self(self):
        field = PrimaryKeyField()
        result = field(object)
        self.assertIs(result, field)

    def test_all_forms_on_class(self):
        class Demo:
            @primary_key
            def id(self):
                ...

            @primary_key()
            def id2(self):
                ...

            id3 = primary_key()

            @char_field(max_length=100)
            def name(self):
                ...

            name2 = char_field(max_length=100)

            @integer_field()
            def age(self):
                ...

        self.assertIsInstance(Demo.__dict__["id"], PrimaryKeyField)
        self.assertIsInstance(Demo.__dict__["id2"], PrimaryKeyField)
        self.assertIsInstance(Demo.__dict__["id3"], PrimaryKeyField)
        self.assertIsInstance(Demo.__dict__["name"], CharField)
        self.assertIsInstance(Demo.__dict__["name2"], CharField)
        self.assertIsInstance(Demo.__dict__["age"], IntegerField)


class TestModelDecorator(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.mkdtemp()
        cls.db = SQLiteAdapter(
            db_directory=cls.temp_dir,
            db_name="test_model_decorator",
            db_name_extension="db",
        )
        cls.db.connect()
        configure(cls.db)

        # Unregister in case of previous test runs
        for name in list(registry.get_all().keys()):
            registry.unregister(name)

    @classmethod
    def tearDownClass(cls):
        cls.db.close()
        for f in os.listdir(cls.temp_dir):
            fp = os.path.join(cls.temp_dir, f)
            if os.path.isfile(fp):
                os.remove(fp)
        os.rmdir(cls.temp_dir)

    def setUp(self):
        for name in list(registry.get_all().keys()):
            registry.unregister(name)

    def test_model_on_plain_class(self):
        @model
        class Item:
            id = primary_key()
            name = char_field(max_length=100)

        self.assertTrue(hasattr(Item, "_fields"))
        self.assertTrue(hasattr(Item, "objects"))
        self.assertTrue(hasattr(Item, "save"))
        self.assertTrue(hasattr(Item, "delete"))
        self.assertTrue(hasattr(Item, "create_table"))
        self.assertTrue(hasattr(Item, "drop_table"))
        self.assertIn("Item", registry.get_all())

    def test_model_with_table_name(self):
        @model(table_name="custom_table")
        class MyModel:
            id = primary_key()

        self.assertEqual(MyModel._table_name, "custom_table")

    def test_model_on_model_subclass(self):
        @model
        class Sub(Model):
            id = primary_key()

        self.assertTrue(hasattr(Sub, "_fields"))
        self.assertIn("Sub", registry.get_all())

    def test_model_with_db_override(self):
        other_db = SQLiteAdapter(
            db_directory=self.temp_dir,
            db_name="other",
            db_name_extension="db",
        )
        other_db.connect()

        @model(db=other_db)
        class OtherModel:
            id = primary_key()
            name = char_field(max_length=100)

        self.assertIs(OtherModel._db, other_db)

        OtherModel.create_table()
        obj = OtherModel.objects.create(name="test")
        self.assertIsNotNone(obj.id)
        OtherModel.drop_table()
        other_db.close()

        db_file = os.path.join(self.temp_dir, "other.db")
        if os.path.exists(db_file):
            os.remove(db_file)

    def test_crud_with_decorators(self):
        @model
        class Product:
            id = primary_key()
            name = char_field(max_length=100, null=False)
            price = integer_field(null=False)

        Product.create_table()

        # Create
        p = Product.objects.create(name="Test", price=100)
        self.assertIsNotNone(p.id)

        # Read
        found = Product.objects.get(id=p.id)
        self.assertEqual(found.name, "Test")

        # Update
        found.price = 200
        found.save()
        updated = Product.objects.get(id=p.id)
        self.assertEqual(updated.price, 200)

        # Filter
        results = Product.objects.filter(price=200).all()
        self.assertEqual(len(results), 1)

        # Delete
        found.delete()
        self.assertEqual(Product.objects.count(), 0)

        Product.drop_table()


if __name__ == "__main__":
    unittest.main()
