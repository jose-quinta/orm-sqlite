import os
import sqlite3
import threading
from typing import Optional, List, Any
from src.orm.db.base import DatabaseAdapter
from src.orm.db.dialect import SQLiteDialect
from src.utils.logger import get_logger

class SQLiteAdapter(DatabaseAdapter):
  def __init__(
    self,
    db_directory: Optional[str] = None,
    db_name: Optional[str] = None,
    db_name_extension: Optional[str] = "db"
  ) -> None:
    self.logger = get_logger(__name__)
    self.db_directory = db_directory or "data"
    self.db_name = db_name or os.path.basename(os.getcwd())
    self.db_name_extension = db_name_extension or "db"
    self.database_path = os.path.join(self.db_directory, f"{self.db_name}.{self.db_name_extension}")

    self._local = threading.local()
    self._lock = threading.Lock()
    self._dialect = SQLiteDialect()

    os.makedirs(self.db_directory, exist_ok=True)
    self.logger.info(f"SQLite configured: {self.database_path}")

  def _get_connection(self):
    if not hasattr(self._local, 'connection'):
      conn = sqlite3.connect(
        database=self.database_path,
        timeout=5,
        check_same_thread=False,
        isolation_level=None
      )
      conn.row_factory = sqlite3.Row
      self._local.connection = conn
    return self._local.connection

  def connect(self) -> None:
    try:
      conn = self._get_connection()
      self.logger.info(f"Connected to SQLite: {self.database_path}")
    except sqlite3.Error as e:
      self.logger.error(f"Failed to connect: {e}", exc_info=True)
      raise

  def execute(self, query: str, params: Optional[List[Any]] = None) -> sqlite3.Cursor:
    if params is None:
      params = []

    with self._lock:
      connection = self._get_connection()
      cursor = connection.cursor()
      cursor.execute(query, params)
      return cursor

  def query(self, query: str, params: Optional[List[Any]] = None) -> sqlite3.Cursor:
    if params is None:
      params = []

    with self._lock:
      connection = self._get_connection()
      cursor = connection.cursor()
      cursor.execute(query, params)
      return cursor

  def commit(self) -> None:
    with self._lock:
      self._get_connection().commit()

  def rollback(self) -> None:
    with self._lock:
      self._get_connection().rollback()

  def get_dialect(self) -> SQLiteDialect:
    return self._dialect

  def set_isolation_level(self, level: str) -> None:
    level = level.upper()
    valid = {"READ UNCOMMITTED", "READ COMMITTED", "REPEATABLE READ", "SERIALIZABLE"}
    if level not in valid:
      raise ValueError(f"Invalid isolation level: {level}")
    if level == "READ UNCOMMITTED":
      self.execute("PRAGMA read_uncommitted = 1")
    else:
      self.execute("PRAGMA read_uncommitted = 0")

  def close(self) -> None:
    with self._lock:
      if hasattr(self._local, 'connection'):
        try:
          self._local.connection.close()
          self.logger.info("Connection closed")
        except sqlite3.Error as e:
          self.logger.error(f"Failed to close: {e}", exc_info=True)
        finally:
          del self._local.connection
