import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import unittest
from src.orm.fields import (
  CharField,
  IntegerField,
  FloatField,
  BooleanField,
  DateTimeField,
  TextField,
  PrimaryKeyField
)
from src.orm.exceptions import FieldError

class TestCharField(unittest.TestCase):
  def test_to_sql(self):
    field = CharField(max_length=100)
    field.name = "name"
    sql = field.to_sql()
    self.assertIn("VARCHAR(100)", sql)

  def test_validate_null_not_allowed(self):
    field = CharField(null=False)
    field.name = "name"
    with self.assertRaises(FieldError):
      field.validate(None)

  def test_validate_max_length(self):
    field = CharField(max_length=5)
    field.name = "name"
    with self.assertRaises(FieldError):
      field.validate("too long")

  def test_validate_valid(self):
    field = CharField(max_length=10)
    field.name = "name"
    self.assertEqual(field.validate("hello"), "hello")

class TestIntegerField(unittest.TestCase):
  def test_to_sql(self):
    field = IntegerField()
    field.name = "age"
    sql = field.to_sql()
    self.assertIn("INTEGER", sql)

  def test_validate_valid(self):
    field = IntegerField()
    field.name = "age"
    self.assertEqual(field.validate(25), 25)

  def test_validate_convert(self):
    field = IntegerField()
    field.name = "age"
    self.assertEqual(field.validate("25"), 25)

  def test_validate_invalid(self):
    field = IntegerField()
    field.name = "age"
    with self.assertRaises(FieldError):
      field.validate("not a number")

class TestFloatField(unittest.TestCase):
  def test_validate_valid(self):
    field = FloatField()
    field.name = "price"
    self.assertEqual(field.validate(10.5), 10.5)

  def test_validate_convert(self):
    field = FloatField()
    field.name = "price"
    self.assertEqual(field.validate("10.5"), 10.5)

class TestBooleanField(unittest.TestCase):
  def test_validate(self):
    field = BooleanField()
    field.name = "active"
    self.assertTrue(field.validate(1))
    self.assertFalse(field.validate(0))

class TestPrimaryKeyField(unittest.TestCase):
  def test_to_sql(self):
    field = PrimaryKeyField()
    field.name = "id"
    sql = field.to_sql()
    self.assertIn("INTEGER PRIMARY KEY AUTOINCREMENT", sql)

if __name__ == "__main__":
  unittest.main()
