from abc import ABC, abstractmethod
from typing import Optional

class Migration(ABC):
  def __init__(self, version: str, description: Optional[str] = None):
    self.version = version
    self.description = description or ""

  @abstractmethod
  def up(self) -> None:
    pass

  @abstractmethod
  def down(self) -> None:
    pass
