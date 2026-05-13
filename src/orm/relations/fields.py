import sys
from typing import Type, Any, Optional
from src.orm.fields import Field
from src.orm.registry import registry
from src.orm.exceptions import FieldError


class ForeignKey(Field):
    def __init__(
        self,
        to: Type,
        related_name: Optional[str] = None,
        on_delete: str = "CASCADE",
        on_update: Optional[str] = None,
        null: bool = False,
        default: Any = None,
    ) -> None:
        super().__init__(null=null, default=default)
        self.to = to
        self._related_name = related_name
        self.on_delete = on_delete
        self.on_update = on_update
        self.fk_column: Optional[str] = None
        self.owner: Optional[Type] = None

    def __set_name__(self, owner: Type, name: str) -> None:
        super().__set_name__(owner, name)
        self.fk_column = f"{name}_id"
        self.owner = owner

    def contribute(self, owner: Type, name: str) -> None:
        self.owner = owner
        self.name = name
        self.fk_column = f"{name}_id"
        self._setup_reverse(owner)

    def _setup_reverse(self, owner: Type) -> None:
        from src.orm.relations.related import RelatedManager

        rel_name = self._related_name or f"{owner.__name__.lower()}_set"
        if not hasattr(self.to, rel_name):
            setattr(self.to, rel_name, RelatedManager(self, rel_name))

    def __get__(self, instance: Any, owner: Type) -> Any:
        if instance is None:
            return self
        cache_key = f"_{self.name}_cached"
        cached = instance.__dict__.get(cache_key)
        if cached is not None:
            return cached
        pk_value = instance.__dict__.get(self.fk_column)
        if pk_value is None:
            return None
        pk_name = getattr(self.to, "_pk_field", None) or "id"
        obj = self.to.objects.filter(**{pk_name: pk_value}).first()
        if obj is not None:
            instance.__dict__[cache_key] = obj
        return obj

    def __set__(self, instance: Any, value: Any) -> None:
        if isinstance(value, self.to):
            pk_name = getattr(value, "_pk_field", None) or "id"
            instance.__dict__[self.fk_column] = getattr(value, pk_name, None)
            instance.__dict__[f"_{self.name}_cached"] = value
        elif value is None:
            instance.__dict__[self.fk_column] = None
            instance.__dict__.pop(f"_{self.name}_cached", None)
        else:
            instance.__dict__[self.fk_column] = value
            instance.__dict__.pop(f"_{self.name}_cached", None)

    def to_sql(self) -> str:
        pk_name = self._get_pk_name()
        sql = f"{self.fk_column} INTEGER REFERENCES {self.to._table_name}({pk_name})"
        if self.on_delete:
            sql += f" ON DELETE {self.on_delete}"
        if self.on_update:
            sql += f" ON UPDATE {self.on_update}"
        if not self.null:
            sql += " NOT NULL"
        if self.unique:
            sql += " UNIQUE"
        return sql

    def _get_pk_name(self) -> str:
        pk = getattr(self.to, "_pk_field", None)
        if pk:
            return pk
        for n, f in self.to._fields.items():
            if hasattr(f, "auto_increment"):
                return n
        return "id"


class OneToOneField(ForeignKey):
    def __init__(
        self,
        to: Type,
        related_name: Optional[str] = None,
        on_delete: str = "CASCADE",
        null: bool = False,
    ) -> None:
        super().__init__(to=to, related_name=related_name, on_delete=on_delete, null=null)

    def _setup_reverse(self, owner: Type) -> None:
        rel_name = self._related_name or f"{owner.__name__.lower()}"
        setattr(self.to, rel_name, _OneToOneReverseDescriptor(self, rel_name))

    def to_sql(self) -> str:
        return super().to_sql() + " UNIQUE"


class _OneToOneReverseDescriptor:
    def __init__(self, fk_field: ForeignKey, rel_name: str) -> None:
        self.fk_field = fk_field
        self._accessor_name = rel_name

    def __get__(self, instance: Any, owner: Type) -> Any:
        if instance is None:
            return self
        cache_key = f"_{self._accessor_name}_cached"
        cached = instance.__dict__.get(cache_key)
        if cached is not None:
            return cached
        pk_name = getattr(instance, "_pk_field", None) or "id"
        results = self.fk_field.owner.objects.filter(
            **{self.fk_field.fk_column: getattr(instance, pk_name)}
        ).all()
        obj = results[0] if results else None
        if obj is not None:
            instance.__dict__[cache_key] = obj
        return obj


class ManyToManyField:
    def __init__(
        self,
        to: Type,
        related_name: Optional[str] = None,
    ) -> None:
        self.to = to
        self._related_name = related_name
        self.owner: Optional[Type] = None
        self.name: Optional[str] = None
        self.table_name: Optional[str] = None

    def __get__(self, instance: Any, owner: Type) -> Any:
        if instance is None:
            return self
        from src.orm.relations.related import ManyToManyForwardManager
        return ManyToManyForwardManager(self, instance)

    def contribute(self, owner: Type, name: str) -> None:
        from src.orm.relations.related import ManyRelatedManager

        self.owner = owner
        self.name = name
        self.table_name = f"{owner._table_name}_{name}"

        rel_name = self._related_name or f"{name}_set"
        setattr(self.to, rel_name, ManyRelatedManager(self))

    def create_table(self, db: Any) -> None:
        pk1 = self._get_pk_name(self.owner)
        pk2 = self._get_pk_name(self.to)
        t1 = self.owner._table_name
        t2 = self.to._table_name

        query = (
            f"CREATE TABLE IF NOT EXISTS {self.table_name} ("
            f"{t1}_id INTEGER REFERENCES {t1}({pk1}), "
            f"{t2}_id INTEGER REFERENCES {t2}({pk2}), "
            f"PRIMARY KEY ({t1}_id, {t2}_id)"
            f")"
        )
        db.execute(query, [])

    def _get_pk_name(self, model: Type) -> str:
        for n, f in model._fields.items():
            if hasattr(f, "auto_increment"):
                return n
        return "id"
