from src.orm.db.base import DatabaseAdapter
from typing import Optional

_default_db: Optional[DatabaseAdapter] = None

def configure(db_adapter: DatabaseAdapter) -> None:
  global _default_db
  _default_db = db_adapter

def get_default_db() -> Optional[DatabaseAdapter]:
  return _default_db
