from typing import Any, Optional


class Select:
    def __init__(self, columns: Optional[list[str]] = None) -> None:
        self.columns = columns or []

    def add_column(self, column: str) -> "Select":
        self.columns.append(column)
        return self

    def compile(self) -> str:
        if not self.columns:
            return "*"
        return ", ".join(self.columns)


class Condition:
    def __init__(
        self,
        field: str,
        operator: str = "=",
        value: Any = None,
        params: Optional[list[Any]] = None,
    ) -> None:
        self.field = field
        self.operator = operator
        self.value = value
        self.params = params or []

    def compile(self) -> tuple[str, list[Any]]:
        op = self.operator.upper()
        if op == "IN":
            values = self.value if isinstance(self.value, (list, tuple)) else [self.value]
            placeholders = ", ".join(["?"] * len(values))
            return f"{self.field} IN ({placeholders})", list(values)
        return f"{self.field} {self.operator} ?", [self.value]


class RawCondition:
    def __init__(self, sql: str, params: Optional[list[Any]] = None) -> None:
        self.sql = sql
        self.params = params or []

    def compile(self) -> tuple[str, list[Any]]:
        return self.sql, self.params


class Where:
    def __init__(self, connector: str = "AND") -> None:
        self.connector = connector.upper()
        self.children: list[Condition | RawCondition | "Where"] = []

    def add(self, field: str, operator: str = "=", value: Any = None) -> "Where":
        self.children.append(Condition(field, operator, value))
        return self

    def add_raw(self, sql: str, params: Optional[list[Any]] = None) -> "Where":
        self.children.append(RawCondition(sql, params))
        return self

    def add_where(self, where: "Where") -> "Where":
        self.children.append(where)
        return self

    def compile(self) -> tuple[str, list[Any]]:
        if not self.children:
            return "", []

        parts: list[str] = []
        params: list[Any] = []
        for child in self.children:
            if isinstance(child, Where):
                sql, p = child.compile()
                if sql:
                    parts.append(f"({sql})")
                    params.extend(p)
            else:
                sql, p = child.compile()
                if sql:
                    parts.append(sql)
                    params.extend(p)

        if not parts:
            return "", []
        return f" {self.connector} ".join(parts), params


class Join:
    def __init__(
        self,
        table: str,
        on: list[str] | str,
        alias: Optional[str] = None,
        type: str = "LEFT",
    ) -> None:
        self.table = table
        self.alias = alias
        self.type = type.upper()
        if isinstance(on, list) and len(on) == 3:
            self.on = on
            self._raw_on = None
        else:
            self._raw_on = str(on)
            self.on = None

    def compile(self) -> str:
        alias_clause = f" AS {self.alias}" if self.alias else ""
        if self._raw_on is not None:
            on_clause = self._raw_on
        else:
            on_clause = f"{self.on[0]} {self.on[1]} {self.on[2]}"
        return f"{self.type} JOIN {self.table}{alias_clause} ON {on_clause}"


class OrderBy:
    def __init__(self, fields: Optional[list[str]] = None) -> None:
        self.fields = fields or []

    def add(self, field: str, direction: Optional[str] = None) -> "OrderBy":
        if direction:
            self.fields.append(f"{field} {direction}")
        else:
            self.fields.append(field)
        return self

    def compile(self) -> str:
        if not self.fields:
            return ""
        return ", ".join(self.fields)


class Limit:
    def __init__(self, value: int) -> None:
        self.value = value


class Offset:
    def __init__(self, value: int) -> None:
        self.value = value


class CompiledQuery:
    def __init__(self, sql: str, params: Optional[list[Any]] = None) -> None:
        self.sql = sql
        self.params = params or []
