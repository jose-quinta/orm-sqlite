from __future__ import annotations
import threading
from typing import Any, Optional
from urllib.parse import urlparse

from src.orm.db.base import DatabaseAdapter
from src.orm.db.dialect import PostgreSQLDialect
from src.utils.logger import get_logger


class PostgreSQLAdapter(DatabaseAdapter):
    def __init__(
        self,
        dsn: Optional[str] = None,
        host: str = "localhost",
        port: int = 5432,
        dbname: str = "postgres",
        user: str = "postgres",
        password: str = "",
        minconn: int = 1,
        maxconn: int = 10,
    ) -> None:
        self.logger = get_logger(__name__)
        self._dialect = PostgreSQLDialect()
        self._pool = None
        self._minconn = minconn
        self._maxconn = maxconn
        self._lock = threading.Lock()
        self._local = threading.local()

        if dsn:
            parsed = urlparse(dsn)
            self.host = parsed.hostname or "localhost"
            self.port = parsed.port or 5432
            self.dbname = parsed.path.lstrip("/") or "postgres"
            self.user = parsed.username or "postgres"
            self.password = parsed.password or ""
        else:
            self.host = host
            self.port = port
            self.dbname = dbname
            self.user = user
            self.password = password

        self.logger.info(
            f"PostgreSQL configured: {self.user}@{self.host}:{self.port}/{self.dbname}"
        )

    def _get_pool(self):
        if self._pool is None:
            import psycopg2.pool
            with self._lock:
                if self._pool is None:
                    self._pool = psycopg2.pool.ThreadedConnectionPool(
                        self._minconn,
                        self._maxconn,
                        host=self.host,
                        port=self.port,
                        dbname=self.dbname,
                        user=self.user,
                        password=self.password,
                    )
        return self._pool

    def _get_connection(self):
        if not hasattr(self._local, "connection") or self._local.connection is None:
            pool = self._get_pool()
            self._local.connection = pool.getconn()
        return self._local.connection

    def _release_if_held(self) -> None:
        if hasattr(self._local, "connection") and self._local.connection is not None:
            if self._pool:
                self._pool.putconn(self._local.connection)
            self._local.connection = None

    def connect(self) -> None:
        import psycopg2
        try:
            conn = self._get_connection()
            cur = conn.cursor()
            cur.execute("SELECT 1")
            cur.close()
            self.logger.info(
                f"Connected to PostgreSQL: {self.host}:{self.port}/{self.dbname}"
            )
        except Exception as e:
            self.logger.error(f"Failed to connect to PostgreSQL: {e}", exc_info=True)
            raise

    def execute(self, query: str, params: Optional[list[Any]] = None) -> Any:
        if params is None:
            params = []
        conn = self._get_connection()
        with self._lock:
            cursor = conn.cursor()
            try:
                cursor.execute(query, params)
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return cursor

    def _execute_no_commit(self, query: str, params: Optional[list[Any]] = None) -> Any:
        if params is None:
            params = []
        conn = self._get_connection()
        with self._lock:
            cursor = conn.cursor()
            try:
                cursor.execute(query, params)
            except Exception:
                conn.rollback()
                raise
        return cursor

    def query(self, query: str, params: Optional[list[Any]] = None) -> Any:
        if params is None:
            params = []
        conn = self._get_connection()
        with self._lock:
            cursor = conn.cursor()
            cursor.execute(query, params)
        return cursor

    def commit(self) -> None:
        conn = self._get_connection()
        with self._lock:
            conn.commit()

    def rollback(self) -> None:
        conn = self._get_connection()
        with self._lock:
            conn.rollback()

    def close(self) -> None:
        self._release_if_held()
        if self._pool:
            with self._lock:
                self._pool.closeall()
                self._pool = None
            self.logger.info("PostgreSQL connection pool closed")

    def set_isolation_level(self, level: str) -> None:
        level = level.upper()
        valid = {"READ UNCOMMITTED", "READ COMMITTED", "REPEATABLE READ", "SERIALIZABLE"}
        if level not in valid:
            raise ValueError(f"Invalid isolation level: {level}")
        self.execute(f"SET SESSION CHARACTERISTICS AS TRANSACTION ISOLATION LEVEL {level}")

    def get_dialect(self) -> PostgreSQLDialect:
        return self._dialect
