from typing import Any
from src.orm.query import QuerySet
from src.orm.exceptions import DoesNotExist, ModelError #type: ignore

class ModelManager:
  def __init__(self, model: object) -> None:
    self.model: object = model

  def get(self, **kwargs: Any) -> object:
    qs = QuerySet(self.model).filter(**kwargs)
    result = qs.first()
    if result is None:
      raise DoesNotExist(f"{self.model.__name__} matching query does not exist") #type: ignore
    return result

  def filter(self, **kwargs: Any) -> QuerySet:
    return QuerySet(self.model).filter(**kwargs)

  def exclude(self, **kwargs: Any) -> QuerySet:
    return QuerySet(self.model).exclude(**kwargs)

  def all(self) -> list[object]:
    return QuerySet(self.model).all()

  def first(self) -> object | None:
    return QuerySet(self.model).first()

  def count(self) -> int:
    return QuerySet(self.model).count()

  def create(self, **kwargs: Any) -> object:
    instance: object = self.model(**kwargs) #type: ignore
    instance.save() #type: ignore
    return instance #type: ignore

  def get_or_create(self, defaults: dict[str, Any] | None = None, **kwargs: Any) -> tuple[object, bool]:
    try:
      return self.get(**kwargs), False
    except DoesNotExist:
      if defaults:
        kwargs.update(defaults)
      return self.create(**kwargs), True

  def aggregate(self, **kwargs: Any) -> dict[str, Any]:
    return QuerySet(self.model).aggregate(**kwargs)

  def exists(self) -> bool:
    return QuerySet(self.model).exists()

  def update(self, **kwargs: Any) -> int:
    return QuerySet(self.model).update(**kwargs)
