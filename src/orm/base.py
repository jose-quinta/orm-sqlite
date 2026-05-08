from typing import Any
from src.orm.db.base import DatabaseAdapter
from src.orm.fields import Field, PrimaryKeyField
from src.orm.manager import ModelManager
from src.orm.registry import registry
from src.orm.config import get_default_db
from src.orm.exceptions import ModelError
from src.orm._methods import init_model, save, delete, create_table, drop_table
from src.orm.setup import setup_model


class Model:
    _table_name: str
    _db: DatabaseAdapter
    _fields: dict[str, Field]
    objects: ModelManager

    def __init__(self, **kwargs: Any) -> None:
        init_model(self, **kwargs)

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        setup_model(cls)

    def save(self) -> None:
        save(self)

    def delete(self) -> None:
        delete(self)

    @classmethod
    def create_table(cls) -> None:
        create_table(cls)

    @classmethod
    def drop_table(cls) -> None:
        drop_table(cls)

    def __repr__(self) -> str:
        fields_repr = {}
        for name in self.__class__._fields:
            value = getattr(self, name, None)
            fields_repr[name] = value
        return f"<{self.__class__.__name__}: {fields_repr}>"
