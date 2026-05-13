from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Optional
from src.orm.relations.fields import ForeignKey, OneToOneField


@dataclass
class ColumnState:
    name: str
    type: str
    nullable: bool
    default: Any
    primary_key: bool
    unique: bool


@dataclass
class IndexState:
    name: str
    fields: list[str]
    unique: bool


@dataclass
class FKState:
    local_column: str
    ref_table: str
    ref_column: str
    on_delete: Optional[str]
    on_update: Optional[str]


@dataclass
class M2MTableState:
    table_name: str
    owner_table: str
    to_table: str
    owner_pk: str
    to_pk: str


@dataclass
class ModelState:
    table_name: str
    columns: list[ColumnState] = field(default_factory=list)
    indexes: list[IndexState] = field(default_factory=list)
    foreign_keys: list[FKState] = field(default_factory=list)
    m2m_tables: list[M2MTableState] = field(default_factory=list)
    check_constraints: list[str] = field(default_factory=list)

    @classmethod
    def from_model(cls, model_class: type) -> "ModelState":
        table = model_class._table_name
        pk_field = getattr(model_class, "_pk_field", None) or "id"
        columns: list[ColumnState] = []
        foreign_keys: list[FKState] = []
        m2m_tables: list[M2MTableState] = []
        indexes: list[IndexState] = []
        check_constraints: list[str] = []

        for name, field in model_class._fields.items():
            if isinstance(field, ForeignKey):
                col_name = field.fk_column
                ref = field.to
                ref_pk = field._get_pk_name()
                columns.append(
                    ColumnState(
                        name=col_name,
                        type="INTEGER",
                        nullable=field.null,
                        default=field.default,
                        primary_key=False,
                        unique=field.unique,
                    )
                )
                foreign_keys.append(
                    FKState(
                        local_column=col_name,
                        ref_table=ref._table_name,
                        ref_column=ref_pk,
                        on_delete=field.on_delete or None,
                        on_update=field.on_update or None,
                    )
                )
            else:
                sql = field.to_sql()
                col_type = _extract_type(sql)
                columns.append(
                    ColumnState(
                        name=name,
                        type=col_type,
                        nullable=field.null,
                        default=field.default,
                        primary_key=getattr(field, "auto_increment", False),
                        unique=field.unique,
                    )
                )

        for name, m2m in getattr(model_class, "_m2m_fields", {}).items():
            owner_pk = m2m._get_pk_name(m2m.owner)
            to_pk = m2m._get_pk_name(m2m.to)
            m2m_tables.append(
                M2MTableState(
                    table_name=m2m.table_name,
                    owner_table=m2m.owner._table_name,
                    to_table=m2m.to._table_name,
                    owner_pk=owner_pk,
                    to_pk=to_pk,
                )
            )

        for idx in getattr(model_class, "_indexes", []):
            idx_name = idx.name or f"idx_{table}_{'_'.join(idx.fields)}"
            indexes.append(
                IndexState(
                    name=idx_name,
                    fields=list(idx.fields),
                    unique=idx.unique,
                )
            )

        for c in getattr(model_class, "_constraints", []):
            from src.orm.constraints import CheckConstraint
            if isinstance(c, CheckConstraint):
                check_constraints.append(c.condition)

        return cls(
            table_name=table,
            columns=columns,
            indexes=indexes,
            foreign_keys=foreign_keys,
            m2m_tables=m2m_tables,
            check_constraints=check_constraints,
        )


def _extract_type(sql: str) -> str:
    parts = sql.split(None, 2)
    return parts[1] if len(parts) > 1 else "TEXT"
