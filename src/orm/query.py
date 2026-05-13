import sys
from typing import Any, Optional
from src.orm.exceptions import QueryError
from src.orm.query_builder import QueryBuilder
from src.orm.query_builder.clauses import Where


class Q:
  def __init__(self, **kwargs: Any) -> None:
    self._children: list = []
    self._connector: str = "AND"
    for key, value in kwargs.items():
      self._children.append(("condition", key, value))

  @classmethod
  def _from_list(cls, children: list, connector: str) -> "Q":
    q = cls()
    q._children = children
    q._connector = connector
    return q

  def __and__(self, other: "Q") -> "Q":
    return Q._from_list([self, other], "AND")

  def __or__(self, other: "Q") -> "Q":
    return Q._from_list([self, other], "OR")

  def __invert__(self) -> "Q":
    q = Q()
    q._connector = "AND"
    q._negated = True
    q._children = [self]
    return q


class QuerySet:
  def __init__(self, model: object) -> None:
    self.model = model
    self._builder = QueryBuilder(model)
    self._select_related: list[str] = []
    self._select_related_built: bool = False
    self._joined_aliases: set[str] = set()
    self._prefetch_related: list[str] = []

  def _fk_fields(self) -> dict:
    return getattr(self.model, "_fk_fields", {})

  def _m2m_fields(self) -> dict:
    return getattr(self.model, "_m2m_fields", {})

  def _is_relation(self, field_name: str) -> bool:
    if field_name in self._fk_fields():
      return True
    m2m_fields = self._m2m_fields()
    if field_name in m2m_fields:
      return True
    descriptor = getattr(self.model, field_name, None)
    if hasattr(descriptor, 'fk_field'):
      return True
    if hasattr(descriptor, 'm2m_field'):
      return True
    return False

  def _ensure_relation_join(self, field_name: str) -> str:
    alias = f"__{field_name}"
    pivot_alias = f"__pivot_{field_name}"
    if alias in self._joined_aliases:
      return alias

    fk_fields = self._fk_fields()
    m2m_fields = self._m2m_fields()

    if field_name in fk_fields:
      fk = fk_fields[field_name]
      pk_name = getattr(fk.to, "_pk_field", None) or "id"
      self._builder.join(
        table=fk.to._table_name,
        on=[f"{self.model._table_name}.{fk.fk_column}", "=", f"{alias}.{pk_name}"],
        alias=alias,
        type="LEFT",
      )
      self._joined_aliases.add(alias)
      return alias

    if field_name in m2m_fields:
      m2m = m2m_fields[field_name]
      pk_name = getattr(self.model, "_pk_field", None) or "id"
      target_pk = m2m._get_pk_name(m2m.to)
      t1 = m2m.owner._table_name
      t2 = m2m.to._table_name
      pivot = m2m.table_name
      self._builder.join(
        table=pivot,
        on=[f"{t1}.{pk_name}", "=", f"{pivot_alias}.{t1}_id"],
        alias=pivot_alias,
        type="LEFT",
      )
      self._builder.join(
        table=t2,
        on=[f"{pivot_alias}.{t2}_id", "=", f"{alias}.{target_pk}"],
        alias=alias,
        type="LEFT",
      )
      self._joined_aliases.update([pivot_alias, alias])
      return alias

    descriptor = getattr(self.model, field_name, None)
    if hasattr(descriptor, 'fk_field'):
      fk = descriptor.fk_field
      pk_name = getattr(self.model, "_pk_field", None) or "id"
      self._builder.join(
        table=fk.owner._table_name,
        on=[f"{self.model._table_name}.{pk_name}", "=", f"{alias}.{fk.fk_column}"],
        alias=alias,
        type="LEFT",
      )
      self._joined_aliases.add(alias)
      return alias

    if hasattr(descriptor, 'm2m_field'):
      m2m = descriptor.m2m_field
      pk_name = getattr(self.model, "_pk_field", None) or "id"
      owner_pk = m2m._get_pk_name(m2m.owner)
      t1 = m2m.owner._table_name
      t2 = m2m.to._table_name
      pivot = m2m.table_name
      self._builder.join(
        table=pivot,
        on=[f"{self.model._table_name}.{pk_name}", "=", f"{pivot_alias}.{t2}_id"],
        alias=pivot_alias,
        type="LEFT",
      )
      self._builder.join(
        table=t1,
        on=[f"{pivot_alias}.{t1}_id", "=", f"{alias}.{owner_pk}"],
        alias=alias,
        type="LEFT",
      )
      self._joined_aliases.update([pivot_alias, alias])
      return alias

    raise QueryError(f"Unknown relation field '{field_name}'")

  def _resolve_target_field(self, field: str, parts: list[str]) -> str:
    target_field = parts[1] if len(parts) > 1 else None
    if target_field == "pk":
      fk_fields = self._fk_fields()
      m2m_fields = self._m2m_fields()
      if field in fk_fields:
        target_field = getattr(fk_fields[field].to, "_pk_field", None) or "id"
      elif field in m2m_fields:
        target_field = m2m_fields[field]._get_pk_name(m2m_fields[field].to)
      else:
        descriptor = getattr(self.model, field, None)
        if hasattr(descriptor, 'fk_field'):
          target_field = getattr(descriptor.fk_field.owner, "_pk_field", None) or "id"
        elif hasattr(descriptor, 'm2m_field'):
          target_field = descriptor.m2m_field._get_pk_name(descriptor.m2m_field.owner)
    return target_field

  def _build_condition(self, key: str, value: Any, operator_map: dict, default_op: str = "=") -> tuple[str, str, Any]:
    parts = key.split("__")
    field = parts[0]
    if field == "pk":
      pk_name = getattr(self.model, "_pk_field", None) or "id"
      parts[0] = pk_name
      field = pk_name
    if self._is_relation(field):
      alias = self._ensure_relation_join(field)
      target_field = self._resolve_target_field(field, parts)
      op_key = parts[2] if len(parts) > 2 else None
      operator = operator_map.get(op_key, default_op)
      return (f"{alias}.{target_field}", operator, value)
    op_key = parts[1] if len(parts) > 1 else None
    operator = operator_map.get(op_key, default_op)
    return (f"{self.model._table_name}.{field}", operator, value)

  def _q_to_where(self, q: Q, operator_map: dict, default_op: str = "=") -> Where:
    negated = getattr(q, "_negated", False)
    where = Where(connector=q._connector)
    for child in q._children:
      if isinstance(child, tuple) and child[0] == "condition":
        _, key, value = child
        f, op, v = self._build_condition(key, value, operator_map, default_op)
        where.add(f, op, v)
      elif isinstance(child, Q):
        where.add_where(self._q_to_where(child, operator_map, default_op))
    if negated:
      sql, params = where.compile()
      negated_where = Where()
      negated_where.add_raw(f"NOT ({sql})", params)
      return negated_where
    return where

  def filter(self, *args: Any, **kwargs: Any) -> "QuerySet":
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

    for arg in args:
      if isinstance(arg, Q):
        self._builder._where.add_where(self._q_to_where(arg, operator_map, "="))
      else:
        raise QueryError(f"Invalid filter argument: {arg}")

    for key, value in kwargs.items():
      f, op, v = self._build_condition(key, value, operator_map, "=")
      self._builder._where.add(f, op, v)
    return self

  def exclude(self, *args: Any, **kwargs: Any) -> "QuerySet":
    operator_map = {
      None: "!=",
      "exact": "!=",
      "gt": "<=",
      "gte": "<",
      "lt": ">=",
      "lte": ">"
    }

    for arg in args:
      if isinstance(arg, Q):
        q_where = self._q_to_where(arg, {None: "=", "exact": "=", "ne": "!=", "gt": ">", "gte": ">=", "lt": "<", "lte": "<=", "like": "LIKE", "in": "IN"}, "=")
        sql, params = q_where.compile()
        self._builder._where.add_raw(f"NOT ({sql})", params)
      else:
        raise QueryError(f"Invalid exclude argument: {arg}")

    for key, value in kwargs.items():
      f, op, v = self._build_condition(key, value, operator_map, "!=")
      self._builder._where.add(f, op, v)
    return self

  def order_by(self, *fields: str) -> "QuerySet":
    self._builder.order_by(*fields)
    return self

  def limit(self, count: int) -> "QuerySet":
    self._builder.limit(count)
    return self

  def offset(self, count: int) -> "QuerySet":
    self._builder.offset(count)
    return self

  def select(self, *columns: str) -> "QuerySet":
    self._builder.select(*columns)
    return self

  def join(self, related_field: str, type: str = "LEFT") -> "QuerySet":
    fk_fields = self._fk_fields()
    if related_field not in fk_fields:
      return self
    fk = fk_fields[related_field]
    alias = f"__{related_field}"
    fk_col = fk.fk_column
    pk_name = getattr(fk.to, "_pk_field", None) or "id"
    self._builder.join(
      table=fk.to._table_name,
      on=[f"{self.model._table_name}.{fk_col}", "=", f"{alias}.{pk_name}"],
      alias=alias,
      type=type,
    )
    return self

  def select_related(self, *fields: str) -> "QuerySet":
    self._select_related = list(fields)
    if self._select_related:
      self._build_select_columns()
    return self

  def prefetch_related(self, *fields: str) -> "QuerySet":
    self._prefetch_related = list(fields)
    return self

  def _build_select_columns(self) -> None:
    self._select_related_built = True
    self._builder._select = type(self._builder._select)()

    for col_name in self.model._fields:
      self._builder.add_select(f"{self.model._table_name}.{col_name} AS {col_name}")

    fk_fields = getattr(self.model, "_fk_fields", {})
    for field_name in self._select_related:
      if field_name not in fk_fields:
        continue
      fk = fk_fields[field_name]
      alias = self._ensure_relation_join(field_name)
      for col_name in fk.to._fields:
        self._builder.add_select(f"{alias}.{col_name} AS {alias}__{col_name}")

  def _build_instance(self, data: dict) -> object:
    obj_data: dict[str, Any] = {}
    related_data: dict[str, dict[str, Any]] = {}
    for key, val in data.items():
      parts = key.split("__")
      if len(parts) >= 3 and parts[0] == "":
        rel_name = parts[1]
        col_name = "__".join(parts[2:])
        related_data.setdefault(rel_name, {})[col_name] = val
      else:
        obj_data[key] = val
    obj = self.model(**obj_data)
    for rel_name, fields in related_data.items():
      fk = self.model._fk_fields.get(rel_name)
      if fk:
        pk_attr = getattr(fk.to, "_pk_field", None) or "id"
        pk_val = fields.get(pk_attr)
        if pk_val is not None:
          try:
            obj.__dict__[f"_{rel_name}_cached"] = fk.to(**fields)
          except Exception:
            pass
    return obj

  def _execute_prefetch(self, results: list[object]) -> None:
    if not results:
      return
    pk_name = getattr(self.model, "_pk_field", None) or "id"
    for field_name in self._prefetch_related:
      self._prefetch_one(results, field_name, pk_name)

  def _prefetch_one(self, results: list[object], field_name: str, pk_name: str) -> None:
    fk_fields = self._fk_fields()
    m2m_fields = getattr(self.model, "_m2m_fields", {})
    descriptor = getattr(self.model, field_name, None)

    if field_name in fk_fields:
      fk = fk_fields[field_name]
      fk_values = set()
      for obj in results:
        val = obj.__dict__.get(fk.fk_column)
        if val is not None:
          fk_values.add(val)
      if not fk_values:
        return
      fk_pk = fk._get_pk_name()
      related_objs = fk.to.objects.filter(**{f"{fk_pk}__in": list(fk_values)}).all()
      obj_map = {getattr(o, fk_pk): o for o in related_objs}
      for obj in results:
        fk_val = obj.__dict__.get(fk.fk_column)
        if fk_val is not None and fk_val in obj_map:
          obj.__dict__[f"_{field_name}_cached"] = obj_map[fk_val]
      return

    if hasattr(descriptor, 'fk_field'):
      from src.orm.relations.fields import OneToOneField
      fk = descriptor.fk_field
      is_o2o = isinstance(fk, OneToOneField)
      pks = [getattr(obj, pk_name) for obj in results if getattr(obj, pk_name, None) is not None]
      if not pks:
        return
      related_model = fk.owner
      fk_col = fk.fk_column
      related_objs = related_model.objects.filter(**{f"{fk_col}__in": pks}).all()
      group = {}
      for ro in related_objs:
        fk_val = getattr(ro, fk_col)
        group.setdefault(fk_val, []).append(ro)
      cache_key = f"_{field_name}_cached"
      for obj in results:
        pk_val = getattr(obj, pk_name)
        related = group.get(pk_val, [])
        if is_o2o:
          obj.__dict__[cache_key] = related[0] if related else None
        else:
          obj.__dict__[cache_key] = related
      return

    if field_name in m2m_fields:
      m2m = m2m_fields[field_name]
      pks = [getattr(obj, pk_name) for obj in results if getattr(obj, pk_name, None) is not None]
      if not pks:
        return
      t1 = m2m.owner._table_name
      t2 = m2m.to._table_name
      placeholders = ",".join("?" for _ in pks)
      try:
        cursor = self.model._db.query(
          f"SELECT {t1}_id, {t2}_id FROM {m2m.table_name} WHERE {t1}_id IN ({placeholders})",
          pks,
        )
      except Exception:
        for obj in results:
          obj.__dict__[f"_{field_name}_cached"] = []
        return
      rows = cursor.fetchall()
      related_ids = set()
      mapping = {}
      for row in rows:
        d = dict(row)
        src = d[f"{t1}_id"]
        tgt = d[f"{t2}_id"]
        mapping.setdefault(src, []).append(tgt)
        related_ids.add(tgt)
      if not related_ids:
        for obj in results:
          obj.__dict__[f"_{field_name}_cached"] = []
        return
      related_pk = m2m._get_pk_name(m2m.to)
      related_objs = m2m.to.objects.filter(**{f"{related_pk}__in": list(related_ids)}).all()
      obj_map = {getattr(o, related_pk): o for o in related_objs}
      for obj in results:
        pk_val = getattr(obj, pk_name)
        target_ids = mapping.get(pk_val, [])
        obj.__dict__[f"_{field_name}_cached"] = [obj_map[tid] for tid in target_ids if tid in obj_map]
      return

    if hasattr(descriptor, 'm2m_field'):
      m2m = descriptor.m2m_field
      pks = [getattr(obj, pk_name) for obj in results if getattr(obj, pk_name, None) is not None]
      if not pks:
        return
      t1 = m2m.owner._table_name
      t2 = m2m.to._table_name
      placeholders = ",".join("?" for _ in pks)
      try:
        cursor = self.model._db.query(
          f"SELECT {t2}_id, {t1}_id FROM {m2m.table_name} WHERE {t2}_id IN ({placeholders})",
          pks,
        )
      except Exception:
        for obj in results:
          obj.__dict__[f"_{m2m.name}_cached"] = []
        return
      rows = cursor.fetchall()
      related_ids = set()
      mapping = {}
      for row in rows:
        d = dict(row)
        src = d[f"{t2}_id"]
        tgt = d[f"{t1}_id"]
        mapping.setdefault(src, []).append(tgt)
        related_ids.add(tgt)
      if not related_ids:
        for obj in results:
          obj.__dict__[f"_{m2m.name}_cached"] = []
        return
      related_pk = m2m._get_pk_name(m2m.owner)
      related_objs = m2m.owner.objects.filter(**{f"{related_pk}__in": list(related_ids)}).all()
      obj_map = {getattr(o, related_pk): o for o in related_objs}
      for obj in results:
        pk_val = getattr(obj, pk_name)
        target_ids = mapping.get(pk_val, [])
        obj.__dict__[f"_{m2m.name}_cached"] = [obj_map[tid] for tid in target_ids if tid in obj_map]
      return

    raise QueryError(f"Cannot prefetch unknown relation '{field_name}'")

  def _build_from_join_where(self) -> tuple[str, list[Any]]:
    sql = f"FROM {self.model._table_name}"

    for j in self._builder._joins:
      sql += f" {j.compile()}"

    params: list[Any] = []
    if self._builder._where:
      where_sql, where_params = self._builder._where.compile()
      if where_sql:
        sql += f" WHERE {where_sql}"
        params = where_params

    return sql, params

  def _build_query(self) -> tuple[str, list[Any]]:
    compiled = self._builder.compile()
    if not self._builder._select.columns and self._builder._joins:
      cols = ", ".join(
        f"{self.model._table_name}.{col_name} AS {col_name}"
        for col_name in self.model._fields
      )
      sql = compiled.sql.replace("SELECT *", f"SELECT {cols}", 1)
      return sql, compiled.params
    return compiled.sql, compiled.params

  def all(self) -> list[object]:
    if self._select_related and not self._select_related_built:
      self._build_select_columns()

    query, params = self._build_query()
    cursor = self.model._db.query(query, params)
    rows = cursor.fetchall()

    if self._select_related:
      results = [self._build_instance(dict(row)) for row in rows]
    else:
      results = [self.model(**dict(row)) for row in rows]

    if self._prefetch_related:
      self._execute_prefetch(results)

    return results

  def first(self) -> object | None:
    self._builder.limit(1)
    results = self.all()
    return results[0] if results else None

  def count(self) -> int:
    table_name = self.model._table_name
    pk_name = getattr(self.model, "_pk_field", None) or "id"
    from_join_where, params = self._build_from_join_where()
    query = f"SELECT COUNT(DISTINCT {table_name}.{pk_name}) {from_join_where}"
    cursor = self.model._db.query(query, params)
    return cursor.fetchone()[0]

  def exists(self) -> bool:
    return self.count() > 0

  def delete(self) -> int:
    table_name = self.model._table_name
    pk_name = getattr(self.model, "_pk_field", None) or "id"
    from_join_where, params = self._build_from_join_where()
    query = f"DELETE FROM {table_name} WHERE {pk_name} IN (SELECT {table_name}.{pk_name} {from_join_where})"
    cursor = self.model._db.execute(query, params)
    return cursor.rowcount

  def update(self, **kwargs: Any) -> int:
    table_name = self.model._table_name
    pk_name = getattr(self.model, "_pk_field", None) or "id"

    set_clause = ", ".join([f"{k} = ?" for k in kwargs])
    set_params = list(kwargs.values())

    from_join_where, where_params = self._build_from_join_where()

    query = f"UPDATE {table_name} SET {set_clause} WHERE {pk_name} IN (SELECT {table_name}.{pk_name} {from_join_where})"
    cursor = self.model._db.execute(query, set_params + where_params)
    return cursor.rowcount

  def aggregate(self, **kwargs: Any) -> dict[str, Any]:
    agg_fields = []
    for alias, expr in kwargs.items():
      agg_fields.append(f"{expr} AS {alias}")

    from_join_where, params = self._build_from_join_where()
    query = f"SELECT {', '.join(agg_fields)} {from_join_where}"
    cursor = self.model._db.query(query, params)
    row = cursor.fetchone()
    return dict(row) if row else {}
