def _get_dialect(obj):
    db = getattr(obj, '_db', None)
    if db is not None and hasattr(db, 'get_dialect'):
        return db.get_dialect()
    return None


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
    dialect = _get_dialect(self)
    ph = dialect.param_style if dialect else "?"

    if self._pk_field and getattr(self, self._pk_field, None):
        pk_value = getattr(self, self._pk_field)
        set_fields = ", ".join([f"{k} = {ph}" for k in fields if k != self._pk_field])
        values = [fields[k] for k in fields if k != self._pk_field] + [pk_value]
        query = f"UPDATE {self._table_name} SET {set_fields} WHERE {self._pk_field} = {ph}"
        self.__class__._db.execute(query, values)
    else:
        column_list = list(fields.keys())
        values = list(fields.values())
        if dialect and self._pk_field:
            query = dialect.compile_upsert(self._table_name, column_list, [self._pk_field])
        elif dialect:
            cols = ", ".join(column_list)
            phs = dialect.placeholders(len(column_list))
            query = f"INSERT INTO {self._table_name} ({cols}) VALUES ({phs})"
        else:
            field_names = ", ".join(column_list)
            placeholders = ", ".join(["?"] * len(column_list))
            query = f"INSERT OR REPLACE INTO {self._table_name} ({field_names}) VALUES ({placeholders})"
        cursor = self.__class__._db.execute(query, values)
        if self._pk_field:
            setattr(self, self._pk_field, cursor.lastrowid)


def delete(self):
    dialect = _get_dialect(self)
    ph = dialect.param_style if dialect else "?"
    if self._pk_field:
        pk_value = getattr(self, self._pk_field)
        query = f"DELETE FROM {self._table_name} WHERE {self._pk_field} = {ph}"
        self.__class__._db.execute(query, [pk_value])


def create_table(cls):
    dialect = cls._db.get_dialect() if hasattr(cls._db, "get_dialect") else None
    fields_sql = []
    for name, field in cls._fields.items():
        fields_sql.append(field.to_sql(dialect=dialect))

    check_items = []
    for c in getattr(cls, "_constraints", []):
        from src.orm.constraints import CheckConstraint
        if isinstance(c, CheckConstraint):
            check_items.append(f"CHECK ({c.condition})")

    all_items = fields_sql + check_items
    if_exists = "IF NOT EXISTS " if (dialect and dialect.supports_if_not_exists) else ""
    query = f"CREATE TABLE {if_exists}{cls._table_name} ({', '.join(all_items)})"
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
    dialect = cls._db.get_dialect() if hasattr(cls._db, "get_dialect") else None
    if dialect:
        sql = dialect.compile_create_index(name, cls._table_name, list(idx.fields), unique=idx.unique)
    else:
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
    dialect = cls._db.get_dialect() if hasattr(cls._db, "get_dialect") else None

    indexes = getattr(cls, "_indexes", [])
    for idx in indexes:
        name = idx.name or f"idx_{cls._table_name}_{'_'.join(idx.fields)}"
        if dialect:
            sql = dialect.compile_drop_index(name)
        else:
            sql = f"DROP INDEX IF EXISTS {name}"
        cls._db.execute(sql, [])

    for c in getattr(cls, "_constraints", []):
        if isinstance(c, UniqueConstraint):
            name = c.name or f"uniq_{cls._table_name}_{'_'.join(c.fields)}"
            if dialect:
                sql = dialect.compile_drop_index(name)
            else:
                sql = f"DROP INDEX IF EXISTS {name}"
            cls._db.execute(sql, [])


def repr_model(self):
    fields_repr = {}
    for name in self.__class__._fields:
        value = getattr(self, name, None)
        fields_repr[name] = value
    return f"<{self.__class__.__name__}: {fields_repr}>"
