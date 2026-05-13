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
  SQLiteAdapter,
  registry,
  Q
)
from src.orm.config import configure

class TestQ(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.mkdtemp()
        cls.db = SQLiteAdapter(
            db_directory=cls.temp_dir,
            db_name="test_q",
            db_name_extension="db",
        )
        cls.db.connect()
        configure(cls.db)

        for name in list(registry.get_all().keys()):
            registry.unregister(name)

        class Item(Model):
            _db = cls.db
            _table_name = 'items'

            id = PrimaryKeyField()
            name = CharField(max_length=100)
            category = CharField(max_length=50)

        cls.Item = Item

        cls.Item.create_table()

    @classmethod
    def tearDownClass(cls):
        cls.db.execute("PRAGMA foreign_keys = OFF", [])
        for m in reversed(list(registry.get_all().values())):
            try:
                m.drop_table()
            except Exception:
                pass
        cls.db.close()
        db_file = os.path.join(cls.temp_dir, "test_q.db")
        if os.path.exists(db_file):
            os.remove(db_file)
        os.rmdir(cls.temp_dir)

    def setUp(self):
        for name in list(registry.get_all().keys()):
            registry.unregister(name)
        for model_cls in [self.Item]:
            try:
                model_cls.drop_table()
            except Exception:
                pass
            model_cls.create_table()
            registry.register(model_cls)

        self.item1 = self.Item.objects.create(name='Alpha', category='A')
        self.item2 = self.Item.objects.create(name='Beta', category='B')
        self.item3 = self.Item.objects.create(name='Gamma', category='A')
        self.item4 = self.Item.objects.create(name='Delta', category='C')

    def test_simple_q(self):
        r = self.Item.objects.filter(Q(name='Alpha')).all()
        assert len(r) == 1 and r[0].name == 'Alpha', f'Test 1 failed: {len(r)}'

    def test_q_with_or(self):
        r = self.Item.objects.filter(Q(name='Alpha') | Q(name='Beta')).all()
        assert len(r) == 2, f'Test 2 failed: {len(r)}'

    def test_q_with_and(self):
        r = self.Item.objects.filter(Q(category='A') & Q(name='Alpha')).all()
        assert len(r) == 1, f'Test 3 failed: {len(r)}'

    def test_q_complex_nesting(self):
        r = self.Item.objects.filter((Q(name='Alpha') | Q(name='Beta')) & Q(category='A')).all()
        assert len(r) == 1 and r[0].name == 'Alpha', f'Test 4 failed: {len(r)}'

    def test_q_with_kwargs_ANDed(self):
        r = self.Item.objects.filter(Q(category='A'), name='Alpha').all()
        assert len(r) == 1, f'Test 5 failed: {len(r)}'

    def test_q_with_exclude(self):
        r = self.Item.objects.exclude(Q(category='A')).all()
        assert len(r) == 2, f'Test 6 failed: {len(r)}'

    def test_q_with_count(self):
        r = self.Item.objects.filter(Q(category='A')).count()
        assert r == 2, f'Test 7 failed: {r}'


if __name__ == "__main__":
    unittest.main()
