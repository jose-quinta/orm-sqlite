import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import unittest
import os
import tempfile
from src.connection.sqlite import Database

class TestDatabaseConnection(unittest.TestCase):
  def setUp(self):
    self.temp_dir = tempfile.mkdtemp()
    self.db_path = os.path.join(self.temp_dir, "test.db")

  def tearDown(self):
    if os.path.exists(self.db_path):
      os.remove(self.db_path)
    os.rmdir(self.temp_dir)

  def test_connection_creation(self):
    db = Database(
      db_directory=self.temp_dir,
      db_name="test",
      db_name_extension="db"
    )
    self.assertIsNotNone(db._get_connection())
    db.close_all()

  def test_execute_query(self):
    db = Database(
      db_directory=self.temp_dir,
      db_name="test",
      db_name_extension="db"
    )
    cursor = db.execute("CREATE TABLE test_table (id INTEGER PRIMARY KEY, name TEXT)")
    self.assertIsNotNone(cursor)
    db.close_all()

  def test_query(self):
    db = Database(
      db_directory=self.temp_dir,
      db_name="test",
      db_name_extension="db"
    )
    db.execute("CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT)")
    db.execute("INSERT INTO users (name) VALUES (?)", ["Alice"])

    cursor = db.query("SELECT * FROM users")
    rows = cursor.fetchall()
    self.assertEqual(len(rows), 1)
    self.assertEqual(rows[0]["name"], "Alice")
    db.close_all()

if __name__ == "__main__":
  unittest.main()
