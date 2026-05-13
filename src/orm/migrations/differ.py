from __future__ import annotations
from typing import Any
from src.orm.migrations.state import ModelState, ColumnState, IndexState
from src.orm.migrations.operations import (
    Operation,
    CreateTable,
    AddColumn,
    DropColumn,
    CreateIndex,
    DropIndex,
)


class SchemaDiffer:
    def diff(
        self,
        model_states: dict[str, ModelState],
        db_tables: dict[str, Any],
    ) -> list[Operation]:
        operations: list[Operation] = []

        model_by_table: dict[str, ModelState] = {}
        for ms in model_states.values():
            model_by_table[ms.table_name] = ms

        model_tables = set(model_by_table.keys())
        db_names = set(db_tables.keys())

        for tname in sorted(model_tables - db_names):
            operations.append(CreateTable(model_by_table[tname]))

        for tname in sorted(model_tables & db_names):
            ms = model_by_table[tname]
            db_cols = {c["name"]: c for c in db_tables[tname]["columns"]}
            db_idxs = {i["name"]: i for i in db_tables[tname].get("indexes", [])}
            ops = self._diff_table(tname, ms, db_cols, db_idxs)
            operations.extend(ops)

        for tname in sorted(db_names - model_tables):
            pass

        return operations

    def _diff_table(
        self,
        table: str,
        ms: ModelState,
        db_cols: dict[str, Any],
        db_idxs: dict[str, Any],
    ) -> list[Operation]:
        ops: list[Operation] = []
        model_cols = {c.name: c for c in ms.columns}
        model_idxs = {i.name: i for i in ms.indexes}
        from src.orm.constraints import Index, UniqueConstraint
        from src.orm._methods import _emit_index

        for name in sorted(model_cols.keys() - db_cols.keys()):
            col = model_cols[name]
            ops.append(
                AddColumn(
                    table,
                    {
                        "name": col.name,
                        "type": col.type,
                        "nullable": col.nullable,
                        "unique": col.unique,
                        "default": col.default if col.default is not None else None,
                    },
                )
            )

        for name in sorted(db_cols.keys() - model_cols.keys()):
            ops.append(DropColumn(table, name))

        for name in sorted(model_idxs.keys() - db_idxs.keys()):
            idx = model_idxs[name]
            ops.append(
                CreateIndex(
                    table=table,
                    index_name=idx.name,
                    columns=idx.fields,
                    unique=idx.unique,
                )
            )

        for name in sorted(db_idxs.keys() - model_idxs.keys()):
            if name.startswith("idx_") or name.startswith("uniq_"):
                ops.append(DropIndex(name))

        return ops
