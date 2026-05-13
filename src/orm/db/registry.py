from __future__ import annotations
from typing import Any, Optional
from urllib.parse import urlparse

from src.orm.db.base import DatabaseAdapter
from src.orm.db.sqlite import SQLiteAdapter
from src.orm.db.postgresql import PostgreSQLAdapter
from src.orm.db.mysql import MySQLAdapter
from src.orm.db.url_parser import parse_database_url


_adapter_registry: dict[str, type[DatabaseAdapter]] = {
    "sqlite": SQLiteAdapter,
    "postgresql": PostgreSQLAdapter,
    "postgres": PostgreSQLAdapter,
    "mysql": MySQLAdapter,
    "mysql+pymysql": MySQLAdapter,
}


def create_adapter(url: str, **kwargs: Any) -> DatabaseAdapter:
    parsed = parse_database_url(url)
    scheme = parsed.scheme

    if scheme == "sqlite":
        db_path = parsed.database
        directory, sep, name_ext = db_path.rpartition("/")
        if sep:
            name, _, ext = name_ext.partition(".")
            return SQLiteAdapter(
                db_directory=directory,
                db_name=name,
                db_name_extension=ext or "db",
                **{k: v for k, v in kwargs.items() if k in ("db_name", "db_name_extension")},
            )
        else:
            return SQLiteAdapter(
                db_directory="./data",
                db_name=db_path,
                db_name_extension="db",
            )

    adapter_cls = _adapter_registry.get(scheme)
    if adapter_cls is None:
        raise ValueError(f"Unsupported database scheme: {scheme}")

    if parsed.is_postgresql:
        dsn = _build_dsn(scheme, parsed, default_port=5432)
        return adapter_cls(dsn=dsn, **kwargs)

    if parsed.is_mysql:
        dsn = _build_dsn("mysql", parsed, default_port=3306)
        charset = (parsed.query.get("charset") or [None])[0]
        if charset:
            kwargs.setdefault("charset", charset)
        return adapter_cls(dsn=dsn, **kwargs)

    raise ValueError(f"Unsupported database scheme: {scheme}")


def _build_dsn(scheme: str, parsed: Any, default_port: int) -> str:
    dsn = f"{scheme}://"
    if parsed.username:
        dsn += parsed.username
        if parsed.password:
            dsn += f":{parsed.password}"
        dsn += "@"
    dsn += f"{parsed.host or 'localhost'}:{parsed.port or default_port}/{parsed.database}"
    return dsn


def create_adapter_from_env(env_var: str = "DATABASE_URL", **kwargs: Any) -> DatabaseAdapter:
    import os
    url = os.environ.get(env_var)
    if url is None:
        raise ValueError(f"Environment variable '{env_var}' is not set")
    return create_adapter(url, **kwargs)


def register_adapter(scheme: str, adapter_class: type[DatabaseAdapter]) -> None:
    _adapter_registry[scheme] = adapter_class


def get_adapter_class(scheme: str) -> Optional[type[DatabaseAdapter]]:
    return _adapter_registry.get(scheme)
