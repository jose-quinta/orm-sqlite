import sys
import os
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import unittest
import tempfile
from src.orm.db.dialect import SQLiteDialect, PostgreSQLDialect, MySQLDialect
from src.orm.db.registry import create_adapter, get_adapter_class


class TestDialects(unittest.TestCase):
    def test_sqlite_dialect_basics(self):
        d = SQLiteDialect()
        self.assertEqual(d.name, "sqlite")
        self.assertEqual(d.param_style, "?")
        self.assertEqual(d.quote_identifier("users"), '"users"')
        self.assertTrue(d.supports_if_not_exists)

    def test_sqlite_limit_offset(self):
        d = SQLiteDialect()
        self.assertEqual(d.compile_limit_offset(10), "LIMIT 10")
        self.assertEqual(d.compile_limit_offset(10, 20), "LIMIT 10 OFFSET 20")

    def test_sqlite_auto_increment(self):
        d = SQLiteDialect()
        self.assertEqual(d.auto_increment_sql(), "AUTOINCREMENT")

    def test_sqlite_upsert(self):
        d = SQLiteDialect()
        sql = d.compile_upsert("users", ["id", "name"], ["id"])
        self.assertIn("INSERT OR REPLACE INTO", sql)
        self.assertIn("users", sql)
        self.assertIn("?", sql)

    def test_sqlite_insert_returning(self):
        d = SQLiteDialect()
        self.assertIsNone(d.compile_insert_returning("users", ["id", "name"]))

    def test_sqlite_create_index(self):
        d = SQLiteDialect()
        sql = d.compile_create_index("idx_name", "users", ["name"], unique=False)
        self.assertIn("CREATE INDEX IF NOT EXISTS idx_name ON users(name)", sql)

        sql_unique = d.compile_create_index("idx_name", "users", ["name"], unique=True)
        self.assertIn("CREATE UNIQUE INDEX IF NOT EXISTS idx_name ON users(name)", sql_unique)

    def test_sqlite_drop_index(self):
        d = SQLiteDialect()
        self.assertEqual(d.compile_drop_index("idx_name"), "DROP INDEX IF EXISTS idx_name")

    def test_sqlite_placeholders(self):
        d = SQLiteDialect()
        self.assertEqual(d.placeholders(3), "?, ?, ?")

    def test_sqlite_type_map(self):
        d = SQLiteDialect()
        tm = d.type_map
        self.assertEqual(tm["integer"], "INTEGER")
        self.assertEqual(tm["float"], "REAL")
        self.assertEqual(tm["boolean"], "INTEGER")

    def test_postgresql_dialect_basics(self):
        d = PostgreSQLDialect()
        self.assertEqual(d.name, "postgresql")
        self.assertEqual(d.param_style, "%s")
        self.assertEqual(d.quote_identifier("users"), '"users"')
        self.assertTrue(d.supports_if_not_exists)

    def test_postgresql_limit_offset(self):
        d = PostgreSQLDialect()
        self.assertEqual(d.compile_limit_offset(10), "LIMIT 10")
        self.assertEqual(d.compile_limit_offset(10, 20), "LIMIT 10 OFFSET 20")

    def test_postgresql_auto_increment(self):
        d = PostgreSQLDialect()
        self.assertEqual(d.auto_increment_sql(), "SERIAL")

    def test_postgresql_upsert(self):
        d = PostgreSQLDialect()
        sql = d.compile_upsert("users", ["id", "name", "email"], ["id"])
        self.assertIn("INSERT INTO", sql)
        self.assertIn("ON CONFLICT (id) DO UPDATE", sql)
        self.assertIn("EXCLUDED.name", sql)
        self.assertIn("%s", sql)

    def test_postgresql_insert_returning(self):
        d = PostgreSQLDialect()
        sql = d.compile_insert_returning("users", ["id", "name"])
        self.assertIn("INSERT INTO", sql)
        self.assertIn("RETURNING *", sql)
        self.assertIn("%s", sql)

    def test_postgresql_create_index(self):
        d = PostgreSQLDialect()
        sql = d.compile_create_index("idx_name", "users", ["name"])
        self.assertIn("CREATE INDEX IF NOT EXISTS idx_name ON users(name)", sql)

    def test_postgresql_drop_index(self):
        d = PostgreSQLDialect()
        self.assertEqual(d.compile_drop_index("idx_name"), "DROP INDEX IF EXISTS idx_name")

    def test_postgresql_placeholders(self):
        d = PostgreSQLDialect()
        self.assertEqual(d.placeholders(3), "%s, %s, %s")

    def test_postgresql_type_map(self):
        d = PostgreSQLDialect()
        tm = d.type_map
        self.assertEqual(tm["integer"], "INTEGER")
        self.assertEqual(tm["float"], "DOUBLE PRECISION")
        self.assertEqual(tm["boolean"], "BOOLEAN")
        self.assertEqual(tm["datetime"], "TIMESTAMP")
        self.assertEqual(tm["primary_key"], "SERIAL")

    def test_mysql_dialect_basics(self):
        d = MySQLDialect()
        self.assertEqual(d.name, "mysql")
        self.assertEqual(d.param_style, "%s")
        self.assertEqual(d.quote_identifier("users"), "`users`")
        self.assertFalse(d.supports_if_not_exists)

    def test_mysql_limit_offset(self):
        d = MySQLDialect()
        self.assertEqual(d.compile_limit_offset(10), "LIMIT 10")
        self.assertEqual(d.compile_limit_offset(10, 20), "LIMIT 10 OFFSET 20")

    def test_mysql_auto_increment(self):
        d = MySQLDialect()
        self.assertEqual(d.auto_increment_sql(), "AUTO_INCREMENT")

    def test_mysql_upsert(self):
        d = MySQLDialect()
        sql = d.compile_upsert("users", ["id", "name"], ["id"])
        self.assertIn("REPLACE INTO", sql)
        self.assertIn("%s", sql)

    def test_mysql_insert_returning(self):
        d = MySQLDialect()
        self.assertIsNone(d.compile_insert_returning("users", ["id", "name"]))

    def test_mysql_create_index(self):
        d = MySQLDialect()
        sql = d.compile_create_index("idx_name", "users", ["name"])
        self.assertIn("CREATE INDEX idx_name ON users(name)", sql)

        sql_unique = d.compile_create_index("idx_name", "users", ["name"], unique=True)
        self.assertIn("CREATE UNIQUE INDEX idx_name ON users(name)", sql_unique)

    def test_mysql_drop_index(self):
        d = MySQLDialect()
        self.assertEqual(d.compile_drop_index("idx_name"), "DROP INDEX IF EXISTS idx_name")

    def test_mysql_placeholders(self):
        d = MySQLDialect()
        self.assertEqual(d.placeholders(3), "%s, %s, %s")

    def test_mysql_type_map(self):
        d = MySQLDialect()
        tm = d.type_map
        self.assertEqual(tm["integer"], "INTEGER")
        self.assertEqual(tm["float"], "DOUBLE")
        self.assertEqual(tm["boolean"], "TINYINT(1)")
        self.assertEqual(tm["datetime"], "DATETIME")
        self.assertEqual(tm["primary_key"], "INTEGER")


class TestAdapterFactory(unittest.TestCase):
    def test_create_sqlite_adapter_by_url(self):
        db = create_adapter("sqlite:///data/test.db")
        self.assertEqual(db.get_dialect().name, "sqlite")
        db.close()

    def test_create_postgresql_adapter_by_url(self):
        db = create_adapter("postgresql://user:pass@localhost:5432/mydb")
        self.assertEqual(db.get_dialect().name, "postgresql")

    def test_create_mysql_adapter_by_url(self):
        db = create_adapter("mysql://user:pass@localhost:3306/mydb")
        self.assertEqual(db.get_dialect().name, "mysql")

    def test_create_adapter_unsupported_scheme(self):
        with self.assertRaises(ValueError):
            create_adapter("oracle://user:pass@host/db")

    def test_get_adapter_class(self):
        cls = get_adapter_class("sqlite")
        self.assertIsNotNone(cls)
        self.assertEqual(cls.__name__, "SQLiteAdapter")

    def test_get_adapter_class_unknown(self):
        self.assertIsNone(get_adapter_class("oracle"))

    def test_register_adapter(self):
        from src.orm.db.base import DatabaseAdapter
        class FakeAdapter(DatabaseAdapter):
            def connect(self): pass
            def execute(self, q, p=None): pass
            def query(self, q, p=None): pass
            def commit(self): pass
            def rollback(self): pass
            def close(self): pass
            def get_dialect(self): pass
        from src.orm.db.registry import register_adapter, get_adapter_class
        register_adapter("fake", FakeAdapter)
        self.assertEqual(get_adapter_class("fake"), FakeAdapter)


class TestSQLiteAdapterWithDialect(unittest.TestCase):
    def test_adapter_has_dialect(self):
        from src.orm import SQLiteAdapter
        tmp = tempfile.mkdtemp()
        db = SQLiteAdapter(db_directory=tmp, db_name="test_adapt", db_name_extension="db")
        db.connect()
        dialect = db.get_dialect()
        self.assertIsNotNone(dialect)
        self.assertEqual(dialect.name, "sqlite")
        self.assertEqual(db.param_style, "?")
        db.close()
        os.remove(os.path.join(tmp, "test_adapt.db"))
        os.rmdir(tmp)

    def test_adapter_dialect_used_in_query(self):
        from src.orm import SQLiteAdapter, Model, PrimaryKeyField, CharField, registry
        from src.orm.config import configure
        tmp = tempfile.mkdtemp()
        db = SQLiteAdapter(db_directory=tmp, db_name="test_adapt2", db_name_extension="db")
        db.connect()
        configure(db)
        for name in list(registry.get_all().keys()):
            registry.unregister(name)

        class Item(Model):
            _db = db
            _table_name = "adapt_items"
            id = PrimaryKeyField()
            name = CharField(max_length=50)

        Item.create_table()
        Item.objects.create(name="test")
        row = Item.objects.get(id=1)
        self.assertEqual(row.name, "test")

        db.close()
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


class TestTransactions(unittest.TestCase):
    def test_transaction_context_manager(self):
        from src.orm import SQLiteAdapter, Model, PrimaryKeyField, CharField, registry
        from src.orm.config import configure
        tmp = tempfile.mkdtemp()
        db = SQLiteAdapter(db_directory=tmp, db_name="test_tx", db_name_extension="db")
        db.connect()
        configure(db)
        for name in list(registry.get_all().keys()):
            registry.unregister(name)

        class TxItem(Model):
            _db = db
            _table_name = "tx_items"
            id = PrimaryKeyField()
            name = CharField(max_length=50)

        TxItem.create_table()

        with db.transaction():
            TxItem.objects.create(name="a")
            TxItem.objects.create(name="b")

        self.assertEqual(TxItem.objects.count(), 2)

        db.close()
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

    def test_transaction_rollback_on_error(self):
        from src.orm import SQLiteAdapter, Model, PrimaryKeyField, CharField, registry
        from src.orm.config import configure
        tmp = tempfile.mkdtemp()
        db = SQLiteAdapter(db_directory=tmp, db_name="test_tx2", db_name_extension="db")
        db.connect()
        configure(db)
        for name in list(registry.get_all().keys()):
            registry.unregister(name)

        class TxItem2(Model):
            _db = db
            _table_name = "tx_items2"
            id = PrimaryKeyField()
            name = CharField(max_length=50)

        TxItem2.create_table()

        try:
            with db.transaction():
                TxItem2.objects.create(name="x")
                raise ValueError("rollback")
        except ValueError:
            pass

        self.assertEqual(TxItem2.objects.count(), 0)

        db.close()
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

    def test_savepoint(self):
        from src.orm import SQLiteAdapter
        tmp = tempfile.mkdtemp()
        db = SQLiteAdapter(db_directory=tmp, db_name="test_sp", db_name_extension="db")
        db.connect()

        db.execute("CREATE TABLE IF NOT EXISTS sp_test (id INTEGER, val TEXT)")
        db.execute("DELETE FROM sp_test")

        db.begin()
        db.execute("INSERT INTO sp_test VALUES (1, 'a')")
        db.savepoint("sp1")
        db.execute("INSERT INTO sp_test VALUES (2, 'b')")
        db.rollback_to_savepoint("sp1")
        db.commit()

        rows = db.query("SELECT * FROM sp_test").fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["val"], "a")

        db.close()
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

    def test_nested_transaction(self):
        from src.orm import SQLiteAdapter
        tmp = tempfile.mkdtemp()
        db = SQLiteAdapter(db_directory=tmp, db_name="test_ntx", db_name_extension="db")
        db.connect()

        db.execute("CREATE TABLE IF NOT EXISTS ntx_test (id INTEGER, val TEXT)")
        db.execute("DELETE FROM ntx_test")

        with db.transaction():
            db.execute("INSERT INTO ntx_test VALUES (1, 'outer')")
            with db.nested_transaction():
                db.execute("INSERT INTO ntx_test VALUES (2, 'inner')")
            db.execute("INSERT INTO ntx_test VALUES (3, 'outer2')")

        rows = db.query("SELECT val FROM ntx_test ORDER BY id").fetchall()
        vals = [r["val"] for r in rows]
        self.assertEqual(vals, ["outer", "inner", "outer2"])

        db.close()
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

    def test_nested_transaction_rollback_inner(self):
        from src.orm import SQLiteAdapter
        tmp = tempfile.mkdtemp()
        db = SQLiteAdapter(db_directory=tmp, db_name="test_ntx2", db_name_extension="db")
        db.connect()

        db.execute("CREATE TABLE IF NOT EXISTS ntx_test2 (id INTEGER, val TEXT)")
        db.execute("DELETE FROM ntx_test2")

        with db.transaction():
            db.execute("INSERT INTO ntx_test2 VALUES (1, 'keep')")
            try:
                with db.nested_transaction():
                    db.execute("INSERT INTO ntx_test2 VALUES (2, 'rollback')")
                    raise ValueError("rollback nested")
            except ValueError:
                pass
            db.execute("INSERT INTO ntx_test2 VALUES (3, 'keep2')")

        rows = db.query("SELECT val FROM ntx_test2 ORDER BY id").fetchall()
        vals = [r["val"] for r in rows]
        self.assertEqual(vals, ["keep", "keep2"])

        db.close()
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

    def test_set_isolation_level_sqlite(self):
        from src.orm import SQLiteAdapter
        tmp = tempfile.mkdtemp()
        db = SQLiteAdapter(db_directory=tmp, db_name="test_iso", db_name_extension="db")
        db.connect()
        db.set_isolation_level("READ COMMITTED")
        row = db.query("PRAGMA read_uncommitted").fetchone()
        self.assertEqual(row[0], 0)
        db.set_isolation_level("READ UNCOMMITTED")
        row = db.query("PRAGMA read_uncommitted").fetchone()
        self.assertEqual(row[0], 1)
        db.close()
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

    def test_set_isolation_level_invalid(self):
        from src.orm import SQLiteAdapter
        tmp = tempfile.mkdtemp()
        db = SQLiteAdapter(db_directory=tmp, db_name="test_iso2", db_name_extension="db")
        db.connect()
        with self.assertRaises(ValueError):
            db.set_isolation_level("INVALID")
        db.close()
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
