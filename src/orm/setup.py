from typing import Optional

from src.orm.fields import Field
from src.orm.manager import ModelManager
from src.orm.registry import registry
from src.orm.config import get_default_db
from src.orm.exceptions import ModelError


def setup_model(cls: Optional[object], *, table_name: Optional[str]=None, db: Optional[str]=None):
    if table_name:
        cls._table_name = table_name
    elif not hasattr(cls, '_table_name'):
        cls._table_name = cls.__name__.lower()

    cls._fields = {}
    for name, attr in cls.__dict__.items():
        if isinstance(attr, Field):
            cls._fields[name] = attr
            attr.__set_name__(cls, name)

    cls.objects = ModelManager(cls)

    if db is not None:
        cls._db = db
    elif not hasattr(cls, '_db'):
        default_db = get_default_db()
        if default_db is None:
            raise ModelError(
                f"Model '{cls.__name__}' must have a '_db' attribute "
                "or configure default db with configure()"
            )
        cls._db = default_db

    registry.register(cls)
