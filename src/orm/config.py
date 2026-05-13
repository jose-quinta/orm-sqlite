from typing import Any, Optional
from src.orm.db.base import DatabaseAdapter

_default_db: Optional[DatabaseAdapter] = None
_databases: dict[str, DatabaseAdapter] = {}


def configure(db_adapter: DatabaseAdapter) -> None:
    global _default_db
    _default_db = db_adapter
    _databases["default"] = db_adapter


def get_default_db() -> Optional[DatabaseAdapter]:
    return _default_db


def register_db(name: str, db_adapter: DatabaseAdapter) -> None:
    _databases[name] = db_adapter


def get_db(name: str = "default") -> Optional[DatabaseAdapter]:
    return _databases.get(name)


def get_all_dbs() -> dict[str, DatabaseAdapter]:
    return dict(_databases)


def configure_from_url(url: str, name: str = "default", **kwargs: Any) -> DatabaseAdapter:
    from src.orm.db.registry import create_adapter
    adapter = create_adapter(url, **kwargs)
    if name == "default":
        configure(adapter)
    else:
        register_db(name, adapter)
    return adapter
