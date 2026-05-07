from typing import Any, Optional
from src.orm.exceptions import QueryError

class QuerySet:
  def __init__(self, model: object) -> None:
    self.model = model
    self._filters: list[tuple[str, str, Any]] = []
    self._order_by: list[str] = []
    self._limit_val: int | None = None
    self._offset_val: int | None = None
    self._select_related: list[str] = []

  def filter(self, **kwargs: Any) -> "QuerySet":
    operator_map = {
      None: "=",
      "exact": "=",
      "ne": "!=",
      "gt": ">",
      "gte": ">=",
      "lt": "<",
      "lte": "<=",
      "like": "LIKE",
      "in": "IN"
    }

    for key, value in kwargs.items():
      parts = key.split("__")
      field = parts[0]
      op_key = parts[1] if len(parts) > 1 else None
      operator = operator_map.get(op_key, "=")

      self._filters.append((field, operator, value))
    return self

  def exclude(self, **kwargs: Any) -> "QuerySet":
    operator_map = {
      None: "!=",
      "exact": "!=",
      "gt": "<=",
      "gte": "<",
      "lt": ">=",
      "lte": ">"
    }

    for key, value in kwargs.items():
      parts = key.split("__")
      field = parts[0]
      op_key = parts[1] if len(parts) > 1 else None
      operator = operator_map.get(op_key, "!=")

      self._filters.append((field, operator, value))
    return self

  def order_by(self, *fields: str) -> "QuerySet":
    self._order_by.extend(fields)
    return self

  def limit(self, count: int) -> "QuerySet":
    self._limit_val = count
    return self

  def offset(self, count: int) -> "QuerySet":
    self._offset_val = count
    return self

  def _build_where(self) -> tuple[str, list[Any]]:
    if not self._filters:
      return "", []

    conditions = []
    params = []
    for field, operator, value in self._filters:
      conditions.append(f"{field} {operator} ?")
      params.append(value)

    return "WHERE " + " AND ".join(conditions), params

  def _build_query(self) -> tuple[str, list[Any]]:
    table_name = self.model._table_name
    where_clause, params = self._build_where()

    query = f"SELECT * FROM {table_name} {where_clause}"

    if self._order_by:
      order_fields = ", ".join(self._order_by)
      query += f" ORDER BY {order_fields}"

    if self._limit_val is not None:
      query += f" LIMIT {self._limit_val}"

    if self._offset_val is not None:
      query += f" OFFSET {self._offset_val}"

    return query.strip(), params

  def all(self) -> list[object]:
    query, params = self._build_query()
    cursor = self.model._db.query(query, params)
    rows = cursor.fetchall()
    return [self.model(**dict(row)) for row in rows]

  def first(self) -> object | None:
    self._limit_val = 1
    results = self.all()
    return results[0] if results else None

  def count(self) -> int:
    table_name = self.model._table_name
    where_clause, params = self._build_where()
    query = f"SELECT COUNT(*) FROM {table_name} {where_clause}"
    cursor = self.model._db.query(query, params)
    return cursor.fetchone()[0]

  def exists(self) -> bool:
    return self.count() > 0

  def delete(self) -> int:
    table_name = self.model._table_name
    where_clause, params = self._build_where()
    query = f"DELETE FROM {table_name} {where_clause}"
    cursor = self.model._db.execute(query, params)
    return cursor.rowcount

  def update(self, **kwargs: Any) -> int:
    table_name = self.model._table_name
    where_clause, where_params = self._build_where()

    set_clause = ", ".join([f"{k} = ?" for k in kwargs])
    params = list(kwargs.values()) + where_params

    query = f"UPDATE {table_name} SET {set_clause} {where_clause}"
    cursor = self.model._db.execute(query, params)
    return cursor.rowcount

  def aggregate(self, **kwargs: Any) -> dict[str, Any]:
    table_name = self.model._table_name
    where_clause, params = self._build_where()

    agg_fields = []
    for alias, expr in kwargs.items():
      agg_fields.append(f"{expr} AS {alias}")

    query = f"SELECT {', '.join(agg_fields)} FROM {table_name} {where_clause}"
    cursor = self.model._db.query(query, params)
    row = cursor.fetchone()
    return dict(row) if row else {}
