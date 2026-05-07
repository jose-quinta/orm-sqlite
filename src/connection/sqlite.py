import os
import sqlite3
import threading
from typing import Optional, List, Any

from src.utils.logger import get_logger

class Database:
  def __init__(
    self,
    db_directory: Optional[str] = None,
    db_name: Optional[str] = None,
    db_name_extension: Optional[str] = None
  ) -> None:
    self.logger = get_logger(__name__)

    current_directory = os.getcwd()
    project_name = os.path.basename(current_directory)

    if not db_directory:
      db_directory = "data"

    if not db_name:
      db_name = project_name

    if not db_name_extension:
      db_name_extension = "db"

    self.database_path = os.path.join(db_directory, f"{db_name}.{db_name_extension}")

    os.makedirs(db_directory, exist_ok=True)

    self._local = threading.local()
    self._lock = threading.Lock()

    try:
      self.logger.info(f"Database configured: {self.database_path}")
    except sqlite3.Error as e:
      self.logger.error(f"Failed to configure database: {e}", exc_info=True)
      raise

  def _get_connection(self) -> sqlite3.Connection:
    if not hasattr(self._local, 'connection'):
      conn = sqlite3.connect(
        database=self.database_path,
        timeout=5,
        check_same_thread=False
      )
      conn.row_factory = sqlite3.Row
      self._local.connection = conn
      self.logger.info(f"Successfully connected to database: {self.database_path}")
    return self._local.connection

  def execute(self, query: str, params: Optional[List[Any]] = None) -> sqlite3.Cursor:
    if params is None:
      params = []

    with self._lock:
      connection = self._get_connection()
      cursor = connection.cursor()
      cursor.execute(query, params)
      connection.commit()
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

  def close_connection(self) -> None:
    with self._lock:
      if hasattr(self._local, 'connection'):
        try:
          self._local.connection.close()
          self.logger.info("Thread connection closed")
        except sqlite3.Error as e:
          self.logger.error(f"Failed to close connection: {e}", exc_info=True)
        finally:
          del self._local.connection

  def close_all(self) -> None:
    self.close_connection()
