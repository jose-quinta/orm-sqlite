import os
import re
from typing import List, Optional, Type
from src.orm.migrations.migration import Migration
from src.utils.logger import get_logger

logger = get_logger(__name__)


def _parse_version(v: str) -> tuple:
    nums = re.findall(r"\d+", v)
    parts = tuple(int(x) for x in nums) if nums else (v,)
    return parts


class Migrator:
    def __init__(self, db, migrations_dir: Optional[str] = None):
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

    def load_migrations(self, directory: Optional[str] = None) -> None:
        directory = directory or self.migrations_dir
        if not directory or not os.path.isdir(directory):
            return
        sys_path = os.path.abspath(directory)
        if sys_path not in os.sys.path:
            os.sys.path.insert(0, sys_path)
        for fname in sorted(os.listdir(directory)):
            if fname.endswith(".py") and not fname.startswith("__"):
                mod_name = fname[:-3]
                import importlib
                try:
                    mod = importlib.import_module(mod_name)
                    for attr in dir(mod):
                        obj = getattr(mod, attr)
                        if (
                            isinstance(obj, type)
                            and issubclass(obj, Migration)
                            and obj is not Migration
                        ):
                            self.add_migration(obj)
                except Exception as e:
                    logger.warning(f"Could not load migration {fname}: {e}")

    def _version(self, cls: Type[Migration]) -> str:
        return cls.version or ""

    def migrate(self, target_version: Optional[str] = None) -> None:
        applied = self._get_applied_versions()
        sorted_migrations = sorted(
            self._migrations, key=lambda c: _parse_version(self._version(c))
        )
        for migration_class in sorted_migrations:
            v = self._version(migration_class)
            if v in applied:
                continue
            if target_version and _parse_version(v) > _parse_version(target_version):
                break
            migration = migration_class(db=self.db)
            logger.info(
                f"Applying migration {v}: {migration.description}"
            )
            migration.up()
            self.db.execute(
                "INSERT INTO __migrations__ (version, description) VALUES (?, ?)",
                [v, migration.description],
            )

    def rollback(self, target_version: Optional[str] = None) -> None:
        applied = self._get_applied_versions()
        sorted_migrations = sorted(
            self._migrations,
            key=lambda c: _parse_version(self._version(c)),
            reverse=True,
        )
        for migration_class in sorted_migrations:
            v = self._version(migration_class)
            if v not in applied:
                continue
            if target_version and _parse_version(v) <= _parse_version(target_version):
                break
            migration = migration_class(db=self.db)
            logger.info(f"Rolling back migration {v}")
            migration.down()
            self.db.execute(
                "DELETE FROM __migrations__ WHERE version = ?",
                [v],
            )

    def _get_applied_versions(self) -> List[str]:
        cursor = self.db.query("SELECT version FROM __migrations__")
        return [row["version"] for row in cursor.fetchall()]
