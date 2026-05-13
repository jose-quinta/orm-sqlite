from dataclasses import dataclass
from typing import Any, Optional
from src.orm.db.dialect import Dialect


@dataclass
class ColumnInfo:
    name: str
    type: str
    nullable: bool
    default: Any
    primary_key: bool


@dataclass
class IndexInfo:
    name: str
    unique: bool
    columns: list[str]


@dataclass
class ForeignKeyInfo:
    columns: list[str]
    ref_table: str
    ref_columns: list[str]
    on_delete: Optional[str]
    on_update: Optional[str]


class Inspector:
    def __init__(self, db: Any) -> None:
        self.db = db

    def _get_dialect(self) -> Dialect:
        if hasattr(self.db, "get_dialect"):
            return self.db.get_dialect()
        from src.orm.db.dialect import SQLiteDialect
        return SQLiteDialect()

    def get_table_names(self) -> list[str]:
        dialect = self._get_dialect()
        cursor = self.db.query(dialect.inspect_tables_sql())
        names = []
        for row in cursor.fetchall():
            for v in dict(row).values():
                if isinstance(v, str):
                    names.append(v)
        return names

    def get_columns(self, table: str) -> list[ColumnInfo]:
        dialect = self._get_dialect()
        cursor = self.db.query(dialect.inspect_columns_sql(table))
        result = []
        for row in cursor.fetchall():
            p = dialect.parse_column_row(dict(row))
            result.append(
                ColumnInfo(
                    name=p["name"],
                    type=p["type"],
                    nullable=p["nullable"],
                    default=p["default"],
                    primary_key=p["primary_key"],
                )
            )
        return result

    def get_indexes(self, table: str) -> list[IndexInfo]:
        dialect = self._get_dialect()
        cursor = self.db.query(dialect.inspect_indexes_sql(table))
        result = []
        for row in cursor.fetchall():
            d = dialect.parse_index_row(dict(row))
            name = d["name"]
            unique = d["unique"]
            col_cursor = self.db.query(dialect.inspect_index_columns_sql(name))
            cols = [dialect.parse_index_column_row(dict(r))["name"] for r in col_cursor.fetchall()]
            result.append(IndexInfo(name=name, unique=unique, columns=cols))
        return result

    def get_foreign_keys(self, table: str) -> list[ForeignKeyInfo]:
        dialect = self._get_dialect()
        cursor = self.db.query(dialect.inspect_foreign_keys_sql(table))
        fk_map: dict[int, ForeignKeyInfo] = {}
        for row in cursor.fetchall():
            p = dialect.parse_foreign_key_row(dict(row))
            seq = p["seq"]
            if seq not in fk_map:
                fk_map[seq] = ForeignKeyInfo(
                    columns=[],
                    ref_table=p["table"],
                    ref_columns=[],
                    on_delete=p.get("on_delete") or None,
                    on_update=p.get("on_update") or None,
                )
            fk_map[seq].columns.append(p["from"])
            fk_map[seq].ref_columns.append(p["to"])
        return list(fk_map.values())
