from typing import Type, Any
from src.orm.fields import Field
from src.orm.registry import registry
from src.orm.exceptions import FieldError

class ForeignKey(Field):
  def __init__(
    self,
    to: Type,
    related_name: str = None,
    null: bool = False
  ) -> None:
    super().__init__(null=null)
    self.to = to
    self.related_name = related_name

  def __set_name__(self, owner: Type, name: str) -> None:
    super().__set_name__(owner, name)
    self.owner = owner

    if self.related_name:
      setattr(self.to, self.related_name, RelatedManager(owner, self.to, name))

  def to_sql(self) -> str:
    to_table = self.to._table_name
    to_pk = [n for n, f in self.to._fields.items() if isinstance(f, type(self.to._fields.get('id', None))).__mro__ and 'PrimaryKeyField' in [c.__name__ for c in type(self.to._fields.get('id', None)).__mro__]][0] if hasattr(self.to, '_fields') else 'id'

    if not to_pk:
      to_pk = 'id'

    sql = f"{self.name} INTEGER"
    sql += f" REFERENCES {to_table}({to_pk})"
    if not self.null:
      sql += " NOT NULL"
    return sql

  def validate(self, value: Any) -> Any:
    value = super().validate(value)
    if value is not None:
      if not isinstance(value, (int, self.to)):
        raise FieldError(f"ForeignKey expects {self.to.__name__} instance or integer")
      if isinstance(value, self.to):
        return getattr(value, [n for n, f in self.to._fields.items() if isinstance(f, type(self.to._fields.get('id', None))).__mro__ and 'PrimaryKeyField' in [c.__name__ for c in type(self.to._fields.get('id', None)).__mro__]][0] if hasattr(self.to, '_fields') else 'id')
    return value
