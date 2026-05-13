from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Optional


class Dialect(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @property
    @abstractmethod
    def param_style(self) -> str:
        pass

    @abstractmethod
    def quote_identifier(self, name: str) -> str:
        pass

    def placeholders(self, count: int) -> str:
        return ", ".join(self.param_style for _ in range(count))

    @abstractmethod
    def compile_limit_offset(self, limit: int, offset: int = 0) -> str:
        pass

    @abstractmethod
    def auto_increment_sql(self) -> str:
        pass

    @property
    @abstractmethod
    def type_map(self) -> dict[str, str]:
        pass

    @abstractmethod
    def compile_insert_returning(self, table: str, columns: list[str]) -> Optional[str]:
        pass

    @abstractmethod
    def compile_upsert(
        self,
        table: str,
        columns: list[str],
        conflict_columns: list[str],
    ) -> str:
        pass

    @property
    def supports_if_not_exists(self) -> bool:
        return True

    @abstractmethod
    def compile_create_index(
        self,
        name: str,
        table: str,
        columns: list[str],
        unique: bool = False,
    ) -> str:
        pass

    @abstractmethod
    def compile_drop_index(self, name: str) -> str:
        pass

    # --- Inspector support ---

    @abstractmethod
    def inspect_tables_sql(self) -> str:
        pass

    @abstractmethod
    def inspect_columns_sql(self, table: str) -> str:
        pass

    @abstractmethod
    def inspect_indexes_sql(self, table: str) -> str:
        pass

    @abstractmethod
    def inspect_index_columns_sql(self, index_name: str) -> str:
        pass

    @abstractmethod
    def inspect_foreign_keys_sql(self, table: str) -> str:
        pass

    def parse_column_row(self, row: dict) -> dict:
        return {
            "name": row["name"],
            "type": row["type"],
            "nullable": not row["notnull"],
            "default": row["dflt_value"],
            "primary_key": bool(row["pk"]),
        }

    def parse_index_row(self, row: dict) -> dict:
        return {"name": row["name"], "unique": bool(row["unique"])}

    def parse_index_column_row(self, row: dict) -> dict:
        return {"name": row["name"]}

    def parse_foreign_key_row(self, row: dict) -> dict:
        return {
            "seq": row["seq"],
            "table": row["table"],
            "from": row["from"],
            "to": row["to"],
            "on_update": row.get("on_update"),
            "on_delete": row.get("on_delete"),
        }


class SQLiteDialect(Dialect):
    @property
    def name(self) -> str:
        return "sqlite"

    @property
    def param_style(self) -> str:
        return "?"

    def quote_identifier(self, name: str) -> str:
        return f'"{name}"'

    def compile_limit_offset(self, limit: int, offset: int = 0) -> str:
        if offset:
            return f"LIMIT {limit} OFFSET {offset}"
        return f"LIMIT {limit}"

    def auto_increment_sql(self) -> str:
        return "AUTOINCREMENT"

    @property
    def type_map(self) -> dict[str, str]:
        return {
            "integer": "INTEGER",
            "float": "REAL",
            "boolean": "INTEGER",
            "string": "VARCHAR",
            "text": "TEXT",
            "datetime": "DATETIME",
            "primary_key": "INTEGER",
        }

    def compile_insert_returning(self, table: str, columns: list[str]) -> Optional[str]:
        return None

    def compile_upsert(
        self,
        table: str,
        columns: list[str],
        conflict_columns: list[str],
    ) -> str:
        placeholders = ", ".join("?" for _ in columns)
        col_list = ", ".join(columns)
        return f"INSERT OR REPLACE INTO {table} ({col_list}) VALUES ({placeholders})"

    def compile_create_index(
        self,
        name: str,
        table: str,
        columns: list[str],
        unique: bool = False,
    ) -> str:
        kind = "UNIQUE INDEX" if unique else "INDEX"
        cols = ", ".join(columns)
        return f"CREATE {kind} IF NOT EXISTS {name} ON {table}({cols})"

    def compile_drop_index(self, name: str) -> str:
        return f"DROP INDEX IF EXISTS {name}"

    def inspect_tables_sql(self) -> str:
        return "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"

    def inspect_columns_sql(self, table: str) -> str:
        q = self.quote_identifier(table)
        return f"PRAGMA table_info({q})"

    def inspect_indexes_sql(self, table: str) -> str:
        q = self.quote_identifier(table)
        return f"PRAGMA index_list({q})"

    def inspect_index_columns_sql(self, index_name: str) -> str:
        q = self.quote_identifier(index_name)
        return f"PRAGMA index_info({q})"

    def inspect_foreign_keys_sql(self, table: str) -> str:
        q = self.quote_identifier(table)
        return f"PRAGMA foreign_key_list({q})"


class PostgreSQLDialect(Dialect):
    @property
    def name(self) -> str:
        return "postgresql"

    @property
    def param_style(self) -> str:
        return "%s"

    def quote_identifier(self, name: str) -> str:
        return f'"{name}"'

    def compile_limit_offset(self, limit: int, offset: int = 0) -> str:
        if offset:
            return f"LIMIT {limit} OFFSET {offset}"
        return f"LIMIT {limit}"

    def auto_increment_sql(self) -> str:
        return "SERIAL"

    @property
    def type_map(self) -> dict[str, str]:
        return {
            "integer": "INTEGER",
            "float": "DOUBLE PRECISION",
            "boolean": "BOOLEAN",
            "string": "VARCHAR",
            "text": "TEXT",
            "datetime": "TIMESTAMP",
            "primary_key": "SERIAL",
        }

    def compile_insert_returning(self, table: str, columns: list[str]) -> Optional[str]:
        cols = ", ".join(columns)
        return f"INSERT INTO {table} ({cols}) VALUES ({self.placeholders(len(columns))}) RETURNING *"

    def compile_upsert(
        self,
        table: str,
        columns: list[str],
        conflict_columns: list[str],
    ) -> str:
        cols = ", ".join(columns)
        ph = self.placeholders(len(columns))
        updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in columns)
        conflict = ", ".join(conflict_columns)
        return f"INSERT INTO {table} ({cols}) VALUES ({ph}) ON CONFLICT ({conflict}) DO UPDATE SET {updates}"

    def compile_create_index(
        self,
        name: str,
        table: str,
        columns: list[str],
        unique: bool = False,
    ) -> str:
        kind = "UNIQUE INDEX" if unique else "INDEX"
        cols = ", ".join(columns)
        return f"CREATE {kind} IF NOT EXISTS {name} ON {table}({cols})"

    def compile_drop_index(self, name: str) -> str:
        return f"DROP INDEX IF EXISTS {name}"

    def inspect_tables_sql(self) -> str:
        return "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name"

    def inspect_columns_sql(self, table: str) -> str:
        return f"SELECT column_name, data_type, is_nullable, column_default, ordinal_position FROM information_schema.columns WHERE table_name = '{table}' ORDER BY ordinal_position"

    def inspect_indexes_sql(self, table: str) -> str:
        return f"SELECT indexname AS name, indexdef FROM pg_indexes WHERE tablename = '{table}'"

    def inspect_index_columns_sql(self, index_name: str) -> str:
        return f"SELECT a.attname AS name FROM pg_index i JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey) WHERE i.indexrelid = '{index_name}'::regclass"

    def inspect_foreign_keys_sql(self, table: str) -> str:
        return (
            f"SELECT kcu.column_name AS \"from\", "
            f"ccu.table_name AS \"table\", "
            f"ccu.column_name AS \"to\", "
            f"rc.update_rule AS on_update, "
            f"rc.delete_rule AS on_delete "
            f"FROM information_schema.key_column_usage kcu "
            f"JOIN information_schema.constraint_column_usage ccu "
            f"ON kcu.constraint_name = ccu.constraint_name "
            f"JOIN information_schema.referential_constraints rc "
            f"ON kcu.constraint_name = rc.constraint_name "
            f"WHERE kcu.table_name = '{table}' AND kcu.position_in_unique_constraint IS NOT NULL"
        )

    def parse_column_row(self, row: dict) -> dict:
        return {
            "name": row["column_name"],
            "type": row["data_type"],
            "nullable": row["is_nullable"] == "YES",
            "default": row["column_default"],
            "primary_key": False,
        }

    def parse_index_row(self, row: dict) -> dict:
        # pg_indexes returns indexname as name, and indexdef for uniqueness hint
        return {"name": row["name"], "unique": "UNIQUE " in (row.get("indexdef") or "")}

    def parse_index_column_row(self, row: dict) -> dict:
        return {"name": row["name"]}

    def parse_foreign_key_row(self, row: dict) -> dict:
        return {
            "seq": 0,
            "table": row["table"],
            "from": row["from"],
            "to": row["to"],
            "on_update": row.get("on_update"),
            "on_delete": row.get("on_delete"),
        }


class MySQLDialect(Dialect):
    @property
    def name(self) -> str:
        return "mysql"

    @property
    def param_style(self) -> str:
        return "%s"

    def quote_identifier(self, name: str) -> str:
        return f"`{name}`"

    def compile_limit_offset(self, limit: int, offset: int = 0) -> str:
        if offset:
            return f"LIMIT {limit} OFFSET {offset}"
        return f"LIMIT {limit}"

    def auto_increment_sql(self) -> str:
        return "AUTO_INCREMENT"

    @property
    def type_map(self) -> dict[str, str]:
        return {
            "integer": "INTEGER",
            "float": "DOUBLE",
            "boolean": "TINYINT(1)",
            "string": "VARCHAR",
            "text": "TEXT",
            "datetime": "DATETIME",
            "primary_key": "INTEGER",
        }

    def compile_insert_returning(self, table: str, columns: list[str]) -> Optional[str]:
        return None

    def compile_upsert(
        self,
        table: str,
        columns: list[str],
        conflict_columns: list[str],
    ) -> str:
        placeholders = ", ".join("%s" for _ in columns)
        col_list = ", ".join(columns)
        return f"REPLACE INTO {table} ({col_list}) VALUES ({placeholders})"

    @property
    def supports_if_not_exists(self) -> bool:
        return False

    def compile_create_index(
        self,
        name: str,
        table: str,
        columns: list[str],
        unique: bool = False,
    ) -> str:
        kind = "UNIQUE" if unique else ""
        cols = ", ".join(columns)
        return f"CREATE {kind} INDEX {name} ON {table}({cols})".replace("  ", " ")

    def compile_drop_index(self, name: str) -> str:
        return f"DROP INDEX IF EXISTS {name}"

    def inspect_tables_sql(self) -> str:
        return "SHOW TABLES"

    def inspect_columns_sql(self, table: str) -> str:
        return f"SHOW COLUMNS FROM `{table}`"

    def inspect_indexes_sql(self, table: str) -> str:
        return f"SHOW INDEX FROM `{table}`"

    def inspect_index_columns_sql(self, index_name: str) -> str:
        return f"SELECT COLUMN_NAME AS `name` FROM information_schema.STATISTICS WHERE INDEX_NAME = '{index_name}'"

    def inspect_foreign_keys_sql(self, table: str) -> str:
        return (
            f"SELECT kcu.COLUMN_NAME AS `from`, kcu.REFERENCED_TABLE_NAME AS `table`, "
            f"kcu.REFERENCED_COLUMN_NAME AS `to`, rc.UPDATE_RULE AS on_update, "
            f"rc.DELETE_RULE AS on_delete "
            f"FROM information_schema.REFERENTIAL_CONSTRAINTS rc "
            f"JOIN information_schema.KEY_COLUMN_USAGE kcu "
            f"ON rc.CONSTRAINT_NAME = kcu.CONSTRAINT_NAME "
            f"WHERE kcu.TABLE_NAME = '{table}' AND kcu.REFERENCED_TABLE_NAME IS NOT NULL"
        )

    def parse_column_row(self, row: dict) -> dict:
        return {
            "name": row["Field"],
            "type": row["Type"],
            "nullable": row["Null"] == "YES",
            "default": row["Default"],
            "primary_key": row["Key"] == "PRI",
        }

    def parse_index_row(self, row: dict) -> dict:
        return {"name": row["Key_name"], "unique": not row["Non_unique"]}

    def parse_index_column_row(self, row: dict) -> dict:
        return {"name": row["name"]}

    def parse_foreign_key_row(self, row: dict) -> dict:
        return {
            "seq": 0,
            "table": row["table"],
            "from": row["from"],
            "to": row["to"],
            "on_update": row.get("on_update"),
            "on_delete": row.get("on_delete"),
        }
