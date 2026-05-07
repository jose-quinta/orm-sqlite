from abc import ABC, abstractmethod
from typing import Optional, List, Any

class DatabaseAdapter(ABC):
  @abstractmethod
  def connect(self) -> None:
    pass

  @abstractmethod
  def execute(self, query: str, params: Optional[List[Any]] = None) -> Any:
    pass

  @abstractmethod
  def query(self, query: str, params: Optional[List[Any]] = None) -> Any:
    pass

  @abstractmethod
  def commit(self) -> None:
    pass

  @abstractmethod
  def rollback(self) -> None:
    pass

  @abstractmethod
  def close(self) -> None:
    pass

  def transaction(self):
    return TransactionContext(self)

class TransactionContext:
  def __init__(self, db: DatabaseAdapter):
    self.db = db

  def __enter__(self):
    return self

  def __exit__(self, exc_type, exc_val, exc_tb):
    if exc_type is None:
      self.db.commit()
    else:
      self.db.rollback()
    return False
