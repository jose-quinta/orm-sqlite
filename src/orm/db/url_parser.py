from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse, parse_qs


@dataclass
class DatabaseURL:
    scheme: str
    database: str
    username: Optional[str] = None
    password: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    query: dict[str, list[str]] = field(default_factory=dict)

    @property
    def is_sqlite(self) -> bool:
        return self.scheme == "sqlite"

    @property
    def is_postgresql(self) -> bool:
        return self.scheme in ("postgresql", "postgres")

    @property
    def is_mysql(self) -> bool:
        return self.scheme in ("mysql", "mysql+pymysql")


def parse_database_url(url: str) -> DatabaseURL:
    parsed = urlparse(url)
    scheme = parsed.scheme

    if scheme == "sqlite":
        path = parsed.path
        if parsed.netloc:
            path = parsed.netloc + path
        db = path.lstrip("/") or ":memory:"
        return DatabaseURL(
            scheme="sqlite",
            database=db,
            query=parse_qs(parsed.query),
        )

    username = parsed.username
    password = parsed.password or ""
    host = parsed.hostname or "localhost"
    port = parsed.port
    dbname = parsed.path.lstrip("/") or ""

    return DatabaseURL(
        scheme=scheme,
        database=dbname,
        username=username,
        password=password,
        host=host,
        port=port,
        query=parse_qs(parsed.query),
    )
