from src.orm.exceptions import FieldError

class Field:
  def __init__(
    self,
    null: bool = False,
    default: object = None,
    unique: bool = False
  ) -> None:
    self.null = null
    self.default = default
    self.unique = unique
    self.name: str | None = None
    self.model: object | None = None

  def __set_name__(self, owner: object, name: str) -> None:
    self.name = name
    self.model = owner

  def to_sql(self) -> str:
    raise NotImplementedError

  def validate(self, value: object) -> object:
    if value is None:
      if not self.null and self.default is None:
        raise FieldError(f"Field '{self.name}' cannot be null")
      return self.default
    return value

class PrimaryKeyField(Field):
  def __init__(self) -> None:
    super().__init__(null=False, unique=True)
    self.auto_increment = True

  def to_sql(self) -> str:
    return f"{self.name} INTEGER PRIMARY KEY AUTOINCREMENT"

class CharField(Field):
  def __init__(
    self,
    max_length: int = 255,
    **kwargs: object
  ) -> None:
    super().__init__(**kwargs) #type: ignore
    self.max_length = max_length

  def to_sql(self) -> str:
    sql = f"{self.name} VARCHAR({self.max_length})"
    if not self.null:
      sql += " NOT NULL"
    if self.unique:
      sql += " UNIQUE"
    return sql

  def validate(self, value: object) -> object:
    value = super().validate(value)
    if value is not None and len(str(value)) > self.max_length:
      raise FieldError(f"Value exceeds max_length of {self.max_length}")
    return value

class IntegerField(Field):
  def __init__(self, **kwargs: object) -> None:
    super().__init__(**kwargs) #type: ignore

  def to_sql(self) -> str:
    sql = f"{self.name} INTEGER"
    if not self.null:
      sql += " NOT NULL"
    if self.unique:
      sql += " UNIQUE"
    return sql

  def validate(self, value: object) -> object:
    value = super().validate(value)
    if value is not None:
      try:
        return int(value) #type: ignore
      except (ValueError, TypeError):
        raise FieldError(f"Value must be an integer")
    return value

class FloatField(Field):
  def __init__(self, **kwargs: object) -> None:
    super().__init__(**kwargs) #type: ignore

  def to_sql(self) -> str:
    sql = f"{self.name} REAL"
    if not self.null:
      sql += " NOT NULL"
    if self.unique:
      sql += " UNIQUE"
    return sql

  def validate(self, value: object) -> object:
    value = super().validate(value)
    if value is not None:
      try:
        return float(value) #type: ignore
      except (ValueError, TypeError):
        raise FieldError(f"Value must be a float")
    return value

class BooleanField(Field):
  def __init__(self, **kwargs: object) -> None:
    super().__init__(**kwargs) #type: ignore

  def to_sql(self) -> str:
    sql = f"{self.name} BOOLEAN"
    if not self.null:
      sql += " NOT NULL"
    return sql

  def validate(self, value: object) -> object:
    value = super().validate(value)
    if value is not None:
      return bool(value)
    return value

class DateTimeField(Field):
  def __init__(self, auto_now: bool = False, **kwargs: object) -> None:
    super().__init__(**kwargs) #type: ignore
    self.auto_now = auto_now

  def to_sql(self) -> str:
    sql = f"{self.name} DATETIME"
    if not self.null:
      sql += " NOT NULL"
    return sql

class TextField(Field):
  def __init__(self, **kwargs: object) -> None:
    super().__init__(**kwargs) #type: ignore

  def to_sql(self) -> str:
    sql = f"{self.name} TEXT"
    if not self.null:
      sql += " NOT NULL"
    if self.unique:
      sql += " UNIQUE"
    return sql
