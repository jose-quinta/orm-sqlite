from __future__ import annotations
import threading
from typing import Any, Optional
from urllib.parse import urlparse

from src.orm.db.base import DatabaseAdapter
from src.orm.db.dialect import MySQLDialect
from src.utils.logger import get_logger


class MySQLAdapter(DatabaseAdapter):
    def __init__(
        self,
        dsn: Optional[str] = None,
        host: str = "localhost",
        port: int = 3306,
        dbname: str = "mysql",
        user: str = "root",
        password: str = "",
        charset: str = "utf8mb4",
    ) -> None:
        self.logger = get_logger(__name__)
        self._dialect = MySQLDialect()
        self._lock = threading.Lock()
        self._local = threading.local()
        self._charset = charset

        if dsn:
            parsed = urlparse(dsn)
            self.host = parsed.hostname or "localhost"
            self.port = parsed.port or 3306
            self.dbname = parsed.path.lstrip("/") or "mysql"
            self.user = parsed.username or "root"
            self.password = parsed.password or ""
        else:
            self.host = host
            self.port = port
            self.dbname = dbname
            self.user = user
            self.password = password

        self.logger.info(
            f"MySQL configured: {self.user}@{self.host}:{self.port}/{self.dbname}"
        )

    def _get_connection(self):
        if not hasattr(self._local, "connection") or self._local.connection is None:
            import pymysql
            self._local.connection = pymysql.connect(
                host=self.host,
                port=self.port,
                database=self.dbname,
                user=self.user,
                password=self.password,
                charset=self._charset,
                cursorclass=pymysql.cursors.Cursor,
            )
        return self._local.connection

    def connect(self) -> None:
        import pymysql
        try:
            conn = self._get_connection()
            cur = conn.cursor()
            cur.execute("SELECT 1")
            cur.close()
            self.logger.info(
                f"Connected to MySQL: {self.host}:{self.port}/{self.dbname}"
            )
        except Exception as e:
            self.logger.error(f"Failed to connect to MySQL: {e}", exc_info=True)
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
        conn = getattr(self._local, "connection", None)
        if conn is not None:
            try:
                conn.close()
                self.logger.info("MySQL connection closed")
            except Exception as e:
                self.logger.error(f"Failed to close MySQL: {e}", exc_info=True)
            self._local.connection = None

    def set_isolation_level(self, level: str) -> None:
        level = level.upper()
        valid = {"READ UNCOMMITTED", "READ COMMITTED", "REPEATABLE READ", "SERIALIZABLE"}
        if level not in valid:
            raise ValueError(f"Invalid isolation level: {level}")
        self.execute(f"SET SESSION TRANSACTION ISOLATION LEVEL {level}")

    def get_dialect(self) -> MySQLDialect:
        return self._dialect
