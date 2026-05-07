import os
from typing import List, Type
from src.orm.migrations.migration import Migration
from src.utils.logger import get_logger

logger = get_logger(__name__)

class Migrator:
  def __init__(self, db, migrations_dir: str = "migrations"):
    self.db = db
    self.migrations_dir = migrations_dir
    self._migrations: List[Type[Migration]] = []
    self._ensure_migration_table()

  def _ensure_migration_table(self) -> None:
    self.db.execute("""
      CREATE TABLE IF NOT EXISTS __migrations__ (
        version VARCHAR(50) PRIMARY KEY,
        description TEXT,
        applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
      )
    """)

  def add_migration(self, migration: Type[Migration]) -> None:
    self._migrations.append(migration)

  def migrate(self, target_version: str = None) -> None:
    applied = self._get_applied_versions()

    for migration_class in sorted(self._migrations, key=lambda m: m.version):
      if migration_class.version not in applied:
        if target_version and migration_class.version > target_version:
          break
        migration = migration_class()
        logger.info(f"Applying migration {migration.version}: {migration.description}")
        migration.up()
        self.db.execute(
          "INSERT INTO __migrations__ (version, description) VALUES (?, ?)",
          [migration.version, migration.description]
        )

  def rollback(self, target_version: str = None) -> None:
    applied = self._get_applied_versions()

    for migration_class in sorted(self._migrations, key=lambda m: m.version, reverse=True):
      if migration_class.version in applied:
        if target_version and migration_class.version <= target_version:
          break
        migration = migration_class()
        logger.info(f"Rolling back migration {migration.version}")
        migration.down()
        self.db.execute(
          "DELETE FROM __migrations__ WHERE version = ?",
          [migration.version]
        )

  def _get_applied_versions(self) -> List[str]:
    cursor = self.db.query("SELECT version FROM __migrations__")
    return [row['version'] for row in cursor.fetchall()]
