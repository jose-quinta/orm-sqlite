from __future__ import annotations
import os
import re
from datetime import datetime
from typing import Any
from src.orm.registry import registry
from src.orm.migrations.state import ModelState
from src.orm.migrations.inspector import Inspector
from src.orm.migrations.differ import SchemaDiffer


def _next_version(migrations_dir: str) -> str:
    if not os.path.isdir(migrations_dir):
        return "001"
    max_num = 0
    for fname in os.listdir(migrations_dir):
        m = re.match(r"(\d+)", fname)
        if m:
            num = int(m.group(1))
            if num > max_num:
                max_num = num
    return f"{max_num + 1:03d}"


def _render_operation(op: Any, dialect: Any = None, indent: str = "    ") -> str:
    from src.orm.migrations.operations import (
        CreateTable,
        DropTable,
        AddColumn,
        DropColumn,
        CreateIndex,
        DropIndex,
    )
    from src.orm.db.dialect import SQLiteDialect

    if dialect is None:
        dialect = SQLiteDialect()

    if_not_exists = "IF NOT EXISTS " if dialect.supports_if_not_exists else ""

    if isinstance(op, CreateTable):
        lines = [f'{indent}# Create table {op.model_state.table_name}']
        cols = []
        for c in op.model_state.columns:
            parts = [c.name, c.type]
            if c.primary_key and c.type.upper() == "INTEGER":
                parts.append(f"PRIMARY KEY {dialect.auto_increment_sql()}")
            else:
                if not c.nullable:
                    parts.append("NOT NULL")
                if c.unique:
                    parts.append("UNIQUE")
            cols.append(" ".join(parts))
        for cc in op.model_state.check_constraints:
            cols.append(f"CHECK ({cc})")
        col_sql = ", ".join(cols)
        lines.append(
            f'{indent}self.execute("""CREATE TABLE {if_not_exists}{op.model_state.table_name} ({col_sql})""")'
        )

        for fk in op.model_state.foreign_keys:
            fk_sql = f"{fk.local_column} INTEGER REFERENCES {fk.ref_table}({fk.ref_column})"
            if fk.on_delete:
                fk_sql += f" ON DELETE {fk.on_delete}"
            if fk.on_update:
                fk_sql += f" ON UPDATE {fk.on_update}"
            lines.append(
                f'{indent}self.execute("ALTER TABLE {op.model_state.table_name} ADD COLUMN {fk_sql}")'
            )

        for idx in op.model_state.indexes:
            idx_sql = dialect.compile_create_index(idx.name, op.model_state.table_name, idx.fields, idx.unique)
            lines.append(
                f'{indent}self.execute("{idx_sql}")'
            )

        for m2m in op.model_state.m2m_tables:
            lines.append(
                f'{indent}self.execute("""CREATE TABLE {if_not_exists}{m2m.table_name} ('
                f'{m2m.owner_table}_id INTEGER REFERENCES {m2m.owner_table}({m2m.owner_pk}), '
                f'{m2m.to_table}_id INTEGER REFERENCES {m2m.to_table}({m2m.to_pk}), '
                f'PRIMARY KEY ({m2m.owner_table}_id, {m2m.to_table}_id))""")'
            )
        return "\n".join(lines)

    if isinstance(op, DropTable):
        return f'{indent}self.execute("DROP TABLE IF EXISTS {{self.table_name}}")'

    if isinstance(op, AddColumn):
        parts = [op.column_def["name"], op.column_def["type"]]
        if not op.column_def.get("nullable", True):
            parts.append("NOT NULL")
        if op.column_def.get("unique"):
            parts.append("UNIQUE")
        default = op.column_def.get("default")
        if default is not None:
            parts.append(f"DEFAULT {default}")
        col_sql = " ".join(parts)
        return f'{indent}self.execute("ALTER TABLE {op.table} ADD COLUMN {col_sql}")'

    if isinstance(op, DropColumn):
        return f'{indent}self.execute("ALTER TABLE {op.table} DROP COLUMN {op.column_name}")'

    if isinstance(op, CreateIndex):
        idx_sql = dialect.compile_create_index(op.index_name, op.table, op.columns, op.unique)
        return f'{indent}self.execute("{idx_sql}")'

    if isinstance(op, DropIndex):
        idx_sql = dialect.compile_drop_index(op.index_name)
        return f'{indent}self.execute("{idx_sql}")'

    return f"{indent}pass  # {op.describe()}"


def make_migration(
    db: Any,
    migrations_dir: str = "migrations",
    message: str = "",
) -> str | None:
    if hasattr(db, "get_dialect"):
        dialect = db.get_dialect()
    else:
        from src.orm.db.dialect import SQLiteDialect
        dialect = SQLiteDialect()
    model_states: dict[str, ModelState] = {}
    for name, model_cls in registry.get_all().items():
        model_states[name] = ModelState.from_model(model_cls, dialect=dialect)

    os.makedirs(migrations_dir, exist_ok=True)

    inspector = Inspector(db)
    db_tables: dict[str, Any] = {}
    for tname in inspector.get_table_names():
        if tname.startswith("__"):
            continue
        cols = inspector.get_columns(tname)
        idxs = inspector.get_indexes(tname)
        fks = inspector.get_foreign_keys(tname)
        db_tables[tname] = {
            "columns": [
                {
                    "name": c.name,
                    "type": c.type,
                    "nullable": c.nullable,
                    "default": c.default,
                    "primary_key": c.primary_key,
                }
                for c in cols
            ],
            "indexes": [
                {"name": i.name, "unique": i.unique, "columns": i.columns}
                for i in idxs
            ],
            "foreign_keys": [
                {
                    "columns": f.columns,
                    "ref_table": f.ref_table,
                    "ref_columns": f.ref_columns,
                }
                for f in fks
            ],
        }

    differ = SchemaDiffer()
    operations = differ.diff(model_states, db_tables)
    if not operations:
        return None

    version = _next_version(migrations_dir)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    desc = message or f"Auto-generated migration {version}"

    op_lines = []
    for i, op in enumerate(operations):
        rendered = _render_operation(op, dialect=dialect)
        op_lines.append(rendered)

    up_ops = "\n".join(f"        {line}" for op in operations for line in _render_operation(op, dialect=dialect).split("\n"))
    down_ops_lines = []
    for op in reversed(operations):
        from src.orm.migrations.operations import CreateTable, DropTable, AddColumn, CreateIndex

        if isinstance(op, CreateTable):
            down_ops_lines.append(
                f'        self.execute("DROP TABLE IF EXISTS {op.model_state.table_name}")'
            )
        elif isinstance(op, DropTable):
            down_ops_lines.append(f"        # Cannot reverse DropTable for {op.table_name}")
        elif isinstance(op, AddColumn):
            col_name = op.column_def["name"]
            down_ops_lines.append(
                f'        self.execute("ALTER TABLE {op.table} DROP COLUMN {col_name}")'
            )
        elif isinstance(op, DropColumn):
            down_ops_lines.append(f"        # Cannot reverse DropColumn for {op.column_name}")
        elif isinstance(op, CreateIndex):
            down_ops_lines.append(
                f'        self.execute("{dialect.compile_drop_index(op.index_name)}")'
            )
        elif hasattr(op, "describe"):
            down_ops_lines.append(f"        # No reverse for {op.describe()}")
    down_ops = "\n".join(down_ops_lines)

    code = f'''"""
Migration {version}: {desc}
Generated at: {ts}
"""

from src.orm.migrations import Migration


class Migration{version}(Migration):
    version = "{version}"
    description = "{desc}"

    def up(self):
{up_ops}

    def down(self):
{down_ops}
'''
    filepath = os.path.join(migrations_dir, f"{version}_auto.py")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(code)

    return filepath
