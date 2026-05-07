from typing import List, Any
from src.orm.query import QuerySet

class RelatedManager:
  def __init__(self, from_model: Any, to_model: Any, field_name: str) -> None:
    self.from_model = from_model
    self.to_model = to_model
    self.field_name = field_name

  def filter(self, **kwargs: Any) -> "QuerySet":
    return QuerySet(self.from_model).filter(**kwargs)

  def all(self) -> List[Any]:
    return self.filter().all()
