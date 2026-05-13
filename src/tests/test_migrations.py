import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import unittest
import os
import tempfile
from src.orm import (
    Model, PrimaryKeyField, CharField, IntegerField, FloatField,
    ForeignKey, OneToOneField, Index, SQLiteAdapter, registry,
)
from src.orm.config import configure
from src.orm.migrations import (
    Migration, Migrator,
    Inspector, ColumnInfo, IndexInfo, ForeignKeyInfo,
    ModelState, ColumnState, IndexState,
    CreateTable, DropTable, AddColumn, DropColumn, CreateIndex, DropIndex,
    SchemaDiffer, IrreversibleError,
)


def _make_db():
    tmp = tempfile.mkdtemp()
    db = SQLiteAdapter(db_directory=tmp, db_name="test_migr", db_name_extension="db")
    db.connect()
    os.environ["_TEST_MIGR_TEMP"] = tmp
    return db, tmp


def _clean(db, tmp):
    try:
        db.close()
    except Exception:
        pass
    import time
    time.sleep(0.05)
    for f in os.listdir(tmp):
        fpath = os.path.join(tmp, f)
        try:
            os.remove(fpath)
        except Exception:
            pass
    try:
        os.rmdir(tmp)
    except Exception:
        pass


class TestMigrationBase(unittest.TestCase):
    def test_migration_accepts_db(self):
        class M(Migration):
            version = "001"
            def up(self): pass
            def down(self): pass
        m = M(db="fake")
        self.assertEqual(m.db, "fake")
        self.assertEqual(m.version, "001")

    def test_migration_execute_calls_db(self):
        class FakeDB:
            def execute(self, sql, params):
                self.called = (sql, params)
                return "ok"

        db = FakeDB()
        class M(Migration):
            version = "001"
            def up(self): pass
            def down(self): pass
        m = M(db=db)
        result = m.execute("SELECT 1", [])
        self.assertEqual(db.called, ("SELECT 1", []))
        self.assertEqual(result, "ok")


class TestMigrator(unittest.TestCase):
    def setUp(self):
        self.db, self.tmp = _make_db()
        for name in list(registry.get_all().keys()):
            registry.unregister(name)

    def tearDown(self):
        _clean(self.db, self.tmp)

    def test_migrator_creates_tracking_table(self):
        migrator = Migrator(self.db)
        cols = Inspector(self.db).get_columns("__migrations__")
        self.assertTrue(any(c.name == "version" for c in cols))

    def test_migrate_applies_pending(self):
        applied = []

        class M1(Migration):
            version = "001"
            def up(self):
                applied.append("up1")
                self.execute("CREATE TABLE IF NOT EXISTS _test_m1 (id INTEGER)", [])

            def down(self):
                applied.append("down1")
                self.execute("DROP TABLE IF EXISTS _test_m1", [])

        migrator = Migrator(self.db)
        migrator.add_migration(M1)
        migrator.migrate()
        self.assertIn("up1", applied)
        applied_versions = migrator._get_applied_versions()
        self.assertIn("001", applied_versions)

    def test_migrate_skips_applied(self):
        applied = []

        class M1(Migration):
            version = "001"
            def up(self):
                applied.append("up1")

            def down(self):
                pass

        migrator = Migrator(self.db)
        migrator.add_migration(M1)
        migrator.migrate()
        applied.clear()
        migrator.migrate()
        self.assertEqual(applied, [])

    def test_rollback_reverses(self):
        applied = []

        class M1(Migration):
            version = "001"
            def up(self):
                applied.append("up1")

            def down(self):
                applied.append("down1")

        migrator = Migrator(self.db)
        migrator.add_migration(M1)
        migrator.migrate()
        migrator.rollback()
        self.assertIn("down1", applied)
        self.assertEqual(migrator._get_applied_versions(), [])

    def test_version_sorting_numeric(self):
        class M1(Migration):
            version = "001"
            def up(self): pass
            def down(self): pass

        class M2(Migration):
            version = "002"
            def up(self): pass
            def down(self): pass

        m = Migrator(self.db)
        m.add_migration(M1)
        m.add_migration(M2)
        # Should not raise
        m.migrate()

    def test_load_migrations(self):
        mig_dir = os.path.join(self.tmp, "migs")
        os.makedirs(mig_dir, exist_ok=True)
        with open(os.path.join(mig_dir, "001_test.py"), "w") as f:
            f.write('''
from src.orm.migrations import Migration

class Migration001(Migration):
    version = "001"
    description = "test"
    def up(self): pass
    def down(self): pass
''')
        migrator = Migrator(self.db, migrations_dir=mig_dir)
        migrator.load_migrations()
        self.assertGreater(len(migrator._migrations), 0)


class TestInspector(unittest.TestCase):
    def setUp(self):
        self.db, self.tmp = _make_db()
        for name in list(registry.get_all().keys()):
            registry.unregister(name)

    def tearDown(self):
        _clean(self.db, self.tmp)
        os.environ.pop("_TEST_MIGR_TEMP", None)

    def _create_simple_table(self):
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS _t_inspect ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "name VARCHAR(100) NOT NULL, "
            "age INTEGER DEFAULT 0)"
        )

    def test_get_table_names(self):
        self._create_simple_table()
        ins = Inspector(self.db)
        names = ins.get_table_names()
        self.assertIn("_t_inspect", names)

    def test_get_columns(self):
        self._create_simple_table()
        ins = Inspector(self.db)
        cols = ins.get_columns("_t_inspect")
        id_col = next(c for c in cols if c.name == "id")
        self.assertTrue(id_col.primary_key)
        self.assertIn("INTEGER", id_col.type.upper())
        name_col = next(c for c in cols if c.name == "name")
        self.assertFalse(name_col.nullable)

    def test_get_indexes(self):
        self._create_simple_table()
        self.db.execute(
            "CREATE INDEX IF NOT EXISTS _idx_name ON _t_inspect(name)", []
        )
        ins = Inspector(self.db)
        idxs = ins.get_indexes("_t_inspect")
        names = [i.name for i in idxs]
        self.assertIn("_idx_name", names)

    def test_get_foreign_keys(self):
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS _t_fk_ref (id INTEGER PRIMARY KEY)", []
        )
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS _t_fk_child ("
            "id INTEGER PRIMARY KEY, "
            "ref_id INTEGER REFERENCES _t_fk_ref(id) ON DELETE CASCADE)", []
        )
        ins = Inspector(self.db)
        fks = ins.get_foreign_keys("_t_fk_child")
        self.assertTrue(len(fks) > 0)
        self.assertEqual(fks[0].ref_table, "_t_fk_ref")
        self.assertEqual(fks[0].on_delete, "CASCADE")


class TestModelState(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.db = SQLiteAdapter(
            db_directory=cls.tmp,
            db_name="test_mstate",
            db_name_extension="db",
        )
        cls.db.connect()
        configure(cls.db)
        for name in list(registry.get_all().keys()):
            registry.unregister(name)

        class Product(Model):
            _db = cls.db
            _table_name = "ms_products"
            id = PrimaryKeyField()
            name = CharField(max_length=100, db_index=True)
            price = FloatField(null=True)

        class Order(Model):
            _db = cls.db
            _table_name = "ms_orders"
            id = PrimaryKeyField()
            product = ForeignKey(Product)

        cls.Product = Product
        cls.Order = Order

    @classmethod
    def tearDownClass(cls):
        _clean(cls.db, cls.tmp)

    def test_model_state_has_table_name(self):
        ms = ModelState.from_model(self.Product)
        self.assertEqual(ms.table_name, "ms_products")

    def test_model_state_has_columns(self):
        ms = ModelState.from_model(self.Product)
        names = {c.name for c in ms.columns}
        self.assertIn("id", names)
        self.assertIn("name", names)
        self.assertIn("price", names)

    def test_model_state_has_primary_key(self):
        ms = ModelState.from_model(self.Product)
        pk_cols = [c for c in ms.columns if c.primary_key]
        self.assertEqual(len(pk_cols), 1)
        self.assertEqual(pk_cols[0].name, "id")

    def test_model_state_has_indexes(self):
        ms = ModelState.from_model(self.Product)
        idx_names = {i.name for i in ms.indexes}
        self.assertTrue(
            any("name" in n for n in idx_names),
            f"No index found for 'name' in {idx_names}",
        )

    def test_model_state_has_foreign_keys(self):
        ms = ModelState.from_model(self.Order)
        self.assertTrue(len(ms.foreign_keys) > 0)
        self.assertEqual(ms.foreign_keys[0].ref_table, "ms_products")


class TestOperations(unittest.TestCase):
    def setUp(self):
        self.db, self.tmp = _make_db()
        for name in list(registry.get_all().keys()):
            registry.unregister(name)

    def tearDown(self):
        _clean(self.db, self.tmp)

    def test_create_table_up(self):
        col = ColumnState("id", "INTEGER", False, None, True, False)
        ms = ModelState(table_name="_t_op", columns=[col])
        op = CreateTable(ms)
        op.up(self.db)
        ins = Inspector(self.db)
        self.assertIn("_t_op", ins.get_table_names())

    def test_create_table_down_drops(self):
        col = ColumnState("id", "INTEGER", False, None, True, False)
        ms = ModelState(table_name="_t_op2", columns=[col])
        op = CreateTable(ms)
        op.up(self.db)
        op.down(self.db)
        ins = Inspector(self.db)
        self.assertNotIn("_t_op2", ins.get_table_names())

    def test_add_column(self):
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS _t_ac (id INTEGER PRIMARY KEY)", []
        )
        op = AddColumn("_t_ac", {"name": "score", "type": "INTEGER", "nullable": True, "unique": False})
        op.up(self.db)
        ins = Inspector(self.db)
        cols = ins.get_columns("_t_ac")
        names = {c.name for c in cols}
        self.assertIn("score", names)

    def test_create_index(self):
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS _t_ci (id INTEGER PRIMARY KEY, val INTEGER)", []
        )
        op = CreateIndex("_t_ci", "_idx_val", ["val"])
        op.up(self.db)
        ins = Inspector(self.db)
        idxs = ins.get_indexes("_t_ci")
        names = {i.name for i in idxs}
        self.assertIn("_idx_val", names)

    def test_create_index_down_drops(self):
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS _t_ci2 (id INTEGER PRIMARY KEY, val INTEGER)", []
        )
        op = CreateIndex("_t_ci2", "_idx_val2", ["val"])
        op.up(self.db)
        op.down(self.db)
        ins = Inspector(self.db)
        names = {i.name for i in ins.get_indexes("_t_ci2")}
        self.assertNotIn("_idx_val2", names)

    def test_drop_table_irreversible(self):
        op = DropTable("_t_nonexist")
        with self.assertRaises(IrreversibleError):
            op.down(None)


class TestSchemaDiffer(unittest.TestCase):
    def test_diff_new_table(self):
        col = ColumnState("id", "INTEGER", False, None, True, False)
        ms = ModelState(table_name="new_table", columns=[col])
        differ = SchemaDiffer()
        ops = differ.diff(
            {"NewModel": ms},
            {},
        )
        self.assertTrue(any(isinstance(o, CreateTable) for o in ops))

    def test_diff_add_column(self):
        col = ColumnState("id", "INTEGER", False, None, True, False)
        ms = ModelState(table_name="ex_table", columns=[col])
        db_tables = {
            "ex_table": {
                "columns": [],
                "indexes": [],
                "foreign_keys": [],
            }
        }
        differ = SchemaDiffer()
        ops = differ.diff({"ExModel": ms}, db_tables)
        self.assertTrue(any(isinstance(o, AddColumn) or isinstance(o, CreateTable) for o in ops))

    def test_diff_new_index(self):
        ms = ModelState(
            table_name="t",
            columns=[ColumnState("id", "INTEGER", False, None, True, False)],
            indexes=[IndexState("idx_name", ["name"], False)],
        )
        db_tables = {
            "t": {
                "columns": [{"name": "id", "type": "INTEGER"}],
                "indexes": [],
                "foreign_keys": [],
            }
        }
        differ = SchemaDiffer()
        ops = differ.diff({"M": ms}, db_tables)
        create_idx = [o for o in ops if isinstance(o, CreateIndex)]
        self.assertEqual(len(create_idx), 1)
        self.assertEqual(create_idx[0].index_name, "idx_name")


class TestMakeMigration(unittest.TestCase):
    def setUp(self):
        self.db, self.tmp = _make_db()
        for name in list(registry.get_all().keys()):
            registry.unregister(name)

    def tearDown(self):
        _clean(self.db, self.tmp)

    def test_make_migration_returns_none_when_no_changes(self):
        from src.orm.migrations.autogen import make_migration
        result = make_migration(self.db, migrations_dir=os.path.join(self.tmp, "migs"))
        self.assertIsNone(result)

    def test_make_migration_creates_file(self):
        class M(Model):
            _db = self.db
            _table_name = "mm_test"
            id = PrimaryKeyField()
            name = CharField(max_length=50)

        registry.register(M)
        mig_dir = os.path.join(self.tmp, "migs2")
        from src.orm.migrations.autogen import make_migration
        result = make_migration(self.db, migrations_dir=mig_dir)
        self.assertIsNotNone(result)
        self.assertTrue(os.path.exists(result))
        with open(result) as f:
            content = f.read()
        self.assertIn("class Migration", content)
        self.assertIn("def up", content)
        self.assertIn("def down", content)
        registry.unregister("M")


if __name__ == "__main__":
    unittest.main()
