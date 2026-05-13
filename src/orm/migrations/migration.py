from abc import ABC, abstractmethod
from typing import Any, Optional


class Migration(ABC):
    version = ""
    description = ""

    def __init__(self, db: Any = None) -> None:
        self.db = db

    @abstractmethod
    def up(self) -> None:
        pass

    @abstractmethod
    def down(self) -> None:
        pass

    def execute(self, sql: str, params: Optional[list] = None) -> Any:
        return self.db.execute(sql, params or [])
