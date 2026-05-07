import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import unittest
import os
import tempfile
from src.connection.sqlite import Database
from src.orm import (
  Model,
  CharField,
  IntegerField,
  PrimaryKeyField,
  BooleanField
)

class TestORM(unittest.TestCase):
  @classmethod
  def setUpClass(cls):
    cls.temp_dir = tempfile.mkdtemp()
    cls.db = Database(
      db_directory=cls.temp_dir,
      db_name="test_orm",
      db_name_extension="db"
    )

    class User(Model):
      _db = cls.db
      _table_name = "users"

      id = PrimaryKeyField()
      name = CharField(max_length=100, null=False)
      email = CharField(max_length=255, unique=True)
      age = IntegerField(null=True)
      is_active = BooleanField(default=True)

    cls.User = User
    cls.User.create_table()

  @classmethod
  def tearDownClass(cls):
    cls.db.close_all()
    db_file = os.path.join(cls.temp_dir, "test_orm.db")
    if os.path.exists(db_file):
      os.remove(db_file)
    os.rmdir(cls.temp_dir)

  def setUp(self):
    for u in self.User.objects.all():
      u.delete()

  def test_create_user(self):
    user = self.User.objects.create(
      name="Alice",
      email="alice@test.com",
      age=30
    )
    self.assertEqual(user.name, "Alice")
    self.assertIsNotNone(user.id)

  def test_get_user(self):
    self.User.objects.create(name="Bob", email="bob@test.com", age=25)
    user = self.User.objects.get(email="bob@test.com")
    self.assertEqual(user.name, "Bob")

  def test_filter_users(self):
    self.User.objects.create(name="Alice", email="alice@test.com", age=30, is_active=True)
    self.User.objects.create(name="Bob", email="bob@test.com", age=25, is_active=False)

    active_users = self.User.objects.filter(is_active=True).all()
    self.assertEqual(len(active_users), 1)
    self.assertEqual(active_users[0].name, "Alice")

  def test_update_user(self):
    user = self.User.objects.create(name="Charlie", email="charlie@test.com", age=40)
    user.age = 41
    user.save()

    updated = self.User.objects.get(email="charlie@test.com")
    self.assertEqual(updated.age, 41)

  def test_delete_user(self):
    user = self.User.objects.create(name="Delete Me", email="delete@test.com")
    self.assertEqual(self.User.objects.count(), 1)

    user.delete()
    self.assertEqual(self.User.objects.count(), 0)

  def test_count(self):
    self.User.objects.create(name="User1", email="user1@test.com")
    self.User.objects.create(name="User2", email="user2@test.com")
    self.assertEqual(self.User.objects.count(), 2)

if __name__ == "__main__":
  unittest.main()
