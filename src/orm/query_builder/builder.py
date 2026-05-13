from typing import Any, Optional
from src.orm.query_builder.clauses import (
    Select,
    Where,
    Join,
    OrderBy,
    Limit,
    Offset,
    CompiledQuery,
)


_OPERATOR_MAP = {
    None: "=",
    "exact": "=",
    "ne": "!=",
    "gt": ">",
    "gte": ">=",
    "lt": "<",
    "lte": "<=",
    "like": "LIKE",
    "in": "IN",
}


class QueryBuilder:
    def __init__(self, model: Any) -> None:
        self.model = model
        self._select = Select()
        self._from = model._table_name
        self._joins: list[Join] = []
        self._where = Where()
        self._order_by = OrderBy()
        self._limit: Optional[Limit] = None
        self._offset: Optional[Offset] = None

    def select(self, *columns: str) -> "QueryBuilder":
        self._select = Select(list(columns))
        return self

    def add_select(self, column: str) -> "QueryBuilder":
        self._select.add_column(column)
        return self

    def join(
        self,
        table: str,
        on: list[str] | str,
        alias: Optional[str] = None,
        type: str = "LEFT",
    ) -> "QueryBuilder":
        self._joins.append(Join(table, on, alias, type))
        return self

    def where(self, *args: Any, **kwargs: Any) -> "QueryBuilder":
        if args:
            sql = str(args[0])
            params = list(args[1]) if len(args) > 1 else []
            self._where.add_raw(sql, params)
            return self
        for key, value in kwargs.items():
            parts = key.split("__")
            field = parts[0]
            op_key = parts[1] if len(parts) > 1 else None
            operator = _OPERATOR_MAP.get(op_key, "=")
            self._where.add(field, operator, value)
        return self

    def order_by(self, *fields: str) -> "QueryBuilder":
        for f in fields:
            self._order_by.add(f)
        return self

    def limit(self, value: int) -> "QueryBuilder":
        self._limit = Limit(value)
        return self

    def offset(self, value: int) -> "QueryBuilder":
        self._offset = Offset(value)
        return self

    def compile(self) -> CompiledQuery:
        sql = f"SELECT {self._select.compile()} FROM {self._from}"

        for j in self._joins:
            sql += f" {j.compile()}"

        params: list[Any] = []
        if self._where:
            where_sql, where_params = self._where.compile()
            if where_sql:
                sql += f" WHERE {where_sql}"
                params = where_params

        if self._order_by.fields:
            sql += f" ORDER BY {self._order_by.compile()}"

        if self._limit is not None:
            sql += f" LIMIT {self._limit.value}"

        if self._offset is not None:
            sql += f" OFFSET {self._offset.value}"

        return CompiledQuery(sql, params)
