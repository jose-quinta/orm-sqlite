from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Optional
from src.orm.migrations.state import ModelState


class IrreversibleError(RuntimeError):
    pass


class Operation(ABC):
    @abstractmethod
    def up(self, db: Any) -> None:
        pass

    @abstractmethod
    def down(self, db: Any) -> None:
        pass

    @abstractmethod
    def describe(self) -> str:
        pass


class CreateTable(Operation):
    def __init__(self, model_state: ModelState) -> None:
        self.model_state = model_state

    def up(self, db: Any) -> None:
        ts = self.model_state.table_name
        col_defs = []
        for c in self.model_state.columns:
            parts = [c.name, c.type]
            if c.primary_key and c.type.upper() == "INTEGER":
                parts.append("PRIMARY KEY AUTOINCREMENT")
            else:
                if not c.nullable:
                    parts.append("NOT NULL")
                if c.unique:
                    parts.append("UNIQUE")
            col_defs.append(" ".join(parts))
        for cc in self.model_state.check_constraints:
            col_defs.append(f"CHECK ({cc})")
        sql = f"CREATE TABLE IF NOT EXISTS {ts} ({', '.join(col_defs)})"
        db.execute(sql, [])

        for fk in self.model_state.foreign_keys:
            parts = [
                fk.local_column,
                "INTEGER",
                f"REFERENCES {fk.ref_table}({fk.ref_column})",
            ]
            if fk.on_delete:
                parts.append(f"ON DELETE {fk.on_delete}")
            if fk.on_update:
                parts.append(f"ON UPDATE {fk.on_update}")
            db.execute(
                f"ALTER TABLE {ts} ADD COLUMN {' '.join(parts)}", []
            )

        for idx in self.model_state.indexes:
            kind = "UNIQUE INDEX" if idx.unique else "INDEX"
            cols = ", ".join(idx.fields)
            db.execute(
                f"CREATE {kind} IF NOT EXISTS {idx.name} ON {ts}({cols})", []
            )

        for m2m in self.model_state.m2m_tables:
            db.execute(
                f"CREATE TABLE IF NOT EXISTS {m2m.table_name} ("
                f"{m2m.owner_table}_id INTEGER REFERENCES {m2m.owner_table}({m2m.owner_pk}), "
                f"{m2m.to_table}_id INTEGER REFERENCES {m2m.to_table}({m2m.to_pk}), "
                f"PRIMARY KEY ({m2m.owner_table}_id, {m2m.to_table}_id))",
                [],
            )

    def down(self, db: Any) -> None:
        ts = self.model_state.table_name
        for m2m in self.model_state.m2m_tables:
            db.execute(f"DROP TABLE IF EXISTS {m2m.table_name}", [])
        for idx in self.model_state.indexes:
            db.execute(f"DROP INDEX IF EXISTS {idx.name}", [])
        db.execute(f"DROP TABLE IF EXISTS {ts}", [])

    def describe(self) -> str:
        return f"Create table {self.model_state.table_name}"


class DropTable(Operation):
    def __init__(self, table_name: str) -> None:
        self.table_name = table_name

    def up(self, db: Any) -> None:
        db.execute(f"DROP TABLE IF EXISTS {self.table_name}", [])

    def down(self, db: Any) -> None:
        raise IrreversibleError(
            f"Cannot reverse DropTable for {self.table_name}"
        )

    def describe(self) -> str:
        return f"Drop table {self.table_name}"


class AddColumn(Operation):
    def __init__(self, table: str, column_def: dict) -> None:
        self.table = table
        self.column_def = column_def

    def up(self, db: Any) -> None:
        parts = [self.column_def["name"], self.column_def["type"]]
        if not self.column_def.get("nullable", True):
            parts.append("NOT NULL")
        if self.column_def.get("unique"):
            parts.append("UNIQUE")
        default = self.column_def.get("default")
        if default is not None:
            parts.append(f"DEFAULT {default}")
        sql = f"ALTER TABLE {self.table} ADD COLUMN {' '.join(parts)}"
        db.execute(sql, [])

    def down(self, db: Any) -> None:
        try:
            db.execute(
                f"ALTER TABLE {self.table} DROP COLUMN {self.column_def['name']}",
                [],
            )
        except Exception:
            raise IrreversibleError(
                f"SQLite does not support DROP COLUMN natively"
            )

    def describe(self) -> str:
        return f"Add column {self.column_def['name']} to {self.table}"


class DropColumn(Operation):
    def __init__(self, table: str, column_name: str) -> None:
        self.table = table
        self.column_name = column_name

    def up(self, db: Any) -> None:
        try:
            db.execute(
                f"ALTER TABLE {self.table} DROP COLUMN {self.column_name}",
                [],
            )
        except Exception:
            raise IrreversibleError(
                f"SQLite does not support DROP COLUMN natively"
            )

    def down(self, db: Any) -> None:
        raise IrreversibleError(
            "Cannot reverse DropColumn without column definition"
        )

    def describe(self) -> str:
        return f"Drop column {self.column_name} from {self.table}"


class CreateIndex(Operation):
    def __init__(
        self,
        table: str,
        index_name: str,
        columns: list[str],
        unique: bool = False,
    ) -> None:
        self.table = table
        self.index_name = index_name
        self.columns = columns
        self.unique = unique

    def up(self, db: Any) -> None:
        kind = "UNIQUE INDEX" if self.unique else "INDEX"
        cols = ", ".join(self.columns)
        db.execute(
            f"CREATE {kind} IF NOT EXISTS {self.index_name} ON {self.table}({cols})",
            [],
        )

    def down(self, db: Any) -> None:
        db.execute(f"DROP INDEX IF EXISTS {self.index_name}", [])

    def describe(self) -> str:
        return f"Create index {self.index_name} on {self.table}"


class DropIndex(Operation):
    def __init__(self, index_name: str) -> None:
        self.index_name = index_name

    def up(self, db: Any) -> None:
        db.execute(f"DROP INDEX IF EXISTS {self.index_name}", [])

    def down(self, db: Any) -> None:
        raise IrreversibleError(
            "Cannot reverse DropIndex without index definition"
        )

    def describe(self) -> str:
        return f"Drop index {self.index_name}"
