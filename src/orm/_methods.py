def init_model(self, **kwargs):
    self._pk_field = None
    fk_fields = getattr(self.__class__, "_fk_fields", {})

    for name, field in self.__class__._fields.items():
        value = kwargs.get(name, field.default)
        if hasattr(field, "auto_increment"):
            self._pk_field = name
        setattr(self, name, value)

    for py_name, fk in fk_fields.items():
        if py_name in kwargs:
            setattr(self, py_name, kwargs[py_name])


def get_pk(self):
    if hasattr(self, "_pk_field") and self._pk_field:
        return getattr(self, self._pk_field, None)
    return None


def set_pk(self, value):
    if hasattr(self, "_pk_field") and self._pk_field:
        setattr(self, self._pk_field, value)


def save(self):
    fields = {k: v for k, v in self.__dict__.items() if k in self.__class__._fields}

    if self._pk_field and getattr(self, self._pk_field, None):
        pk_value = getattr(self, self._pk_field)
        set_fields = ", ".join([f"{k} = ?" for k in fields if k != self._pk_field])
        values = [fields[k] for k in fields if k != self._pk_field] + [pk_value]
        query = f"UPDATE {self._table_name} SET {set_fields} WHERE {self._pk_field} = ?"
        self.__class__._db.execute(query, values)
    else:
        field_names = ", ".join(fields.keys())
        placeholders = ", ".join(["?"] * len(fields))
        values = list(fields.values())
        query = f"INSERT OR REPLACE INTO {self._table_name} ({field_names}) VALUES ({placeholders})"
        cursor = self.__class__._db.execute(query, values)
        if self._pk_field:
            setattr(self, self._pk_field, cursor.lastrowid)


def delete(self):
    if self._pk_field:
        pk_value = getattr(self, self._pk_field)
        query = f"DELETE FROM {self._table_name} WHERE {self._pk_field} = ?"
        self.__class__._db.execute(query, [pk_value])


def create_table(cls):
    fields_sql = []
    for name, field in cls._fields.items():
        fields_sql.append(field.to_sql())

    check_items = []
    for c in getattr(cls, "_constraints", []):
        from src.orm.constraints import CheckConstraint
        if isinstance(c, CheckConstraint):
            check_items.append(f"CHECK ({c.condition})")

    all_items = fields_sql + check_items
    query = f"CREATE TABLE IF NOT EXISTS {cls._table_name} ({', '.join(all_items)})"
    cls._db.execute(query, [])

    for m2m in getattr(cls, "_m2m_fields", {}).values():
        m2m.create_table(cls._db)

    _create_indexes(cls)


def _create_indexes(cls):
    from src.orm.constraints import Index, UniqueConstraint

    seen_names = set()
    indexes = getattr(cls, "_indexes", [])

    for idx in indexes:
        if idx.name and idx.name in seen_names:
            continue
        if idx.name:
            seen_names.add(idx.name)
        _emit_index(cls, idx)

    for c in getattr(cls, "_constraints", []):
        if isinstance(c, UniqueConstraint):
            name = c.name or f"uniq_{cls._table_name}_{'_'.join(c.fields)}"
            if name in seen_names:
                continue
            seen_names.add(name)
            _emit_index(cls, Index(*c.fields, name=name, unique=True))


def _emit_index(cls, idx: "Index") -> None:
    from src.orm.constraints import Index
    if not isinstance(idx, Index):
        return
    name = idx.name or f"idx_{cls._table_name}_{'_'.join(idx.fields)}"
    kind = "UNIQUE INDEX" if idx.unique else "INDEX"
    cols = ", ".join(idx.fields)
    sql = f"CREATE {kind} IF NOT EXISTS {name} ON {cls._table_name}({cols})"
    cls._db.execute(sql, [])


def drop_table(cls):
    _drop_indexes(cls)

    for m2m in getattr(cls, "_m2m_fields", {}).values():
        cls._db.execute(f"DROP TABLE IF EXISTS {m2m.table_name}", [])

    query = f"DROP TABLE IF EXISTS {cls._table_name}"
    cls._db.execute(query, [])


def _drop_indexes(cls):
    from src.orm.constraints import Index, UniqueConstraint

    indexes = getattr(cls, "_indexes", [])
    for idx in indexes:
        name = idx.name or f"idx_{cls._table_name}_{'_'.join(idx.fields)}"
        cls._db.execute(f"DROP INDEX IF EXISTS {name}", [])

    for c in getattr(cls, "_constraints", []):
        if isinstance(c, UniqueConstraint):
            name = c.name or f"uniq_{cls._table_name}_{'_'.join(c.fields)}"
            cls._db.execute(f"DROP INDEX IF EXISTS {name}", [])


def repr_model(self):
    fields_repr = {}
    for name in self.__class__._fields:
        value = getattr(self, name, None)
        fields_repr[name] = value
    return f"<{self.__class__.__name__}: {fields_repr}>"
