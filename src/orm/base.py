from typing import Any
from src.orm.db.base import DatabaseAdapter
from src.orm.fields import Field, PrimaryKeyField
from src.orm.manager import ModelManager
from src.orm.registry import registry
from src.orm.config import get_default_db
from src.orm.exceptions import ModelError

class Model:
  _table_name: str
  _db: DatabaseAdapter
  _fields: dict[str, Field]
  objects: ModelManager

  def __init__(self, **kwargs: Any) -> None:
    self._pk_field = None
    for name, field in self.__class__._fields.items():
      value = kwargs.get(name, field.default)
      if isinstance(field, PrimaryKeyField):
        self._pk_field = name
      setattr(self, name, value)

  def __init_subclass__(cls, **kwargs: Any) -> None:
    super().__init_subclass__(**kwargs)

    if not hasattr(cls, "_table_name"):
      cls._table_name = cls.__name__.lower()

    cls._fields = {}
    for name, attr in cls.__dict__.items():
      if isinstance(attr, Field):
        cls._fields[name] = attr
        attr.__set_name__(cls, name)

    cls.objects = ModelManager(cls)

    if not hasattr(cls, "_db"):
      default_db = get_default_db()
      if default_db is None:
        raise ModelError(f"Model '{cls.__name__}' must have a '_db' attribute or configure default db")
      cls._db = default_db

    registry.register(cls)

  def save(self) -> None:
    fields = {k: v for k, v in self.__dict__.items() if k in self.__class__._fields}

    if self._pk_field and getattr(self, self._pk_field, None):
      pk_value = getattr(self, self._pk_field)
      set_fields = ", ".join([f"{k} = ?" for k in fields if k != self._pk_field])
      values = [fields[k] for k in fields if k != self._pk_field] + [pk_value]
      query = f"UPDATE {self._table_name} SET {set_fields} WHERE {self._pk_field} = ?"
      self.__class__._db.execute(query, values)
    else:
      field_names = ", ".join(fields.keys())
      placeholders = ", ".join(["?"] * len(fields))
      values = list(fields.values())
      query = f"INSERT INTO {self._table_name} ({field_names}) VALUES ({placeholders})"
      cursor = self.__class__._db.execute(query, values)
      if self._pk_field:
        setattr(self, self._pk_field, cursor.lastrowid)

  def delete(self) -> None:
    if self._pk_field:
      pk_value = getattr(self, self._pk_field)
      query = f"DELETE FROM {self._table_name} WHERE {self._pk_field} = ?"
      self.__class__._db.execute(query, [pk_value])

  @classmethod
  def create_table(cls) -> None:
    fields_sql = []
    for name, field in cls._fields.items():
      fields_sql.append(field.to_sql())

    query = f"CREATE TABLE IF NOT EXISTS {cls._table_name} ({', '.join(fields_sql)})"
    cls._db.execute(query, [])

  @classmethod
  def drop_table(cls) -> None:
    query = f"DROP TABLE IF EXISTS {cls._table_name}"
    cls._db.execute(query, [])

  def __repr__(self) -> str:
    fields_repr = {}
    for name in self.__class__._fields:
      value = getattr(self, name, None)
      fields_repr[name] = value
    return f"<{self.__class__.__name__}: {fields_repr}>"
