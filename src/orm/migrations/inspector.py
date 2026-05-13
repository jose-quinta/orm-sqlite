from dataclasses import dataclass
from typing import Any, Optional


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

    def get_table_names(self) -> list[str]:
        cursor = self.db.query(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        return [row["name"] for row in cursor.fetchall()]

    def get_columns(self, table: str) -> list[ColumnInfo]:
        cursor = self.db.query(f"PRAGMA table_info(\"{table}\")")
        result = []
        for row in cursor.fetchall():
            d = dict(row)
            result.append(
                ColumnInfo(
                    name=d["name"],
                    type=d["type"],
                    nullable=not d["notnull"],
                    default=d["dflt_value"],
                    primary_key=bool(d["pk"]),
                )
            )
        return result

    def get_indexes(self, table: str) -> list[IndexInfo]:
        cursor = self.db.query(f"PRAGMA index_list(\"{table}\")")
        result = []
        for row in cursor.fetchall():
            d = dict(row)
            name = d["name"]
            unique = bool(d["unique"])
            col_cursor = self.db.query(f"PRAGMA index_info(\"{name}\")")
            cols = [dict(r)["name"] for r in col_cursor.fetchall()]
            result.append(IndexInfo(name=name, unique=unique, columns=cols))
        return result

    def get_foreign_keys(self, table: str) -> list[ForeignKeyInfo]:
        cursor = self.db.query(f"PRAGMA foreign_key_list(\"{table}\")")
        fk_map: dict[int, ForeignKeyInfo] = {}
        for row in cursor.fetchall():
            d = dict(row)
            seq = d["seq"]
            if seq not in fk_map:
                fk_map[seq] = ForeignKeyInfo(
                    columns=[],
                    ref_table=d["table"],
                    ref_columns=[],
                    on_delete=d.get("on_delete") or None,
                    on_update=d.get("on_update") or None,
                )
            fk_map[seq].columns.append(d["from"])
            fk_map[seq].ref_columns.append(d["to"])
        return list(fk_map.values())
