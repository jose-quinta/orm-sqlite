def init_model(self, **kwargs):
    self._pk_field = None
    for name, field in self.__class__._fields.items():
        value = kwargs.get(name, field.default)
        if hasattr(field, 'auto_increment'):
            self._pk_field = name
        setattr(self, name, value)


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
        query = f"INSERT INTO {self._table_name} ({field_names}) VALUES ({placeholders})"
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

    query = f"CREATE TABLE IF NOT EXISTS {cls._table_name} ({', '.join(fields_sql)})"
    cls._db.execute(query, [])


def drop_table(cls):
    query = f"DROP TABLE IF EXISTS {cls._table_name}"
    cls._db.execute(query, [])


def repr_model(self):
    fields_repr = {}
    for name in self.__class__._fields:
        value = getattr(self, name, None)
        fields_repr[name] = value
    return f"<{self.__class__.__name__}: {fields_repr}>"
