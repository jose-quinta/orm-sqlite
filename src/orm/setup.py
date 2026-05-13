from src.orm.fields import Field
from src.orm.manager import ModelManager
from src.orm.registry import registry
from src.orm.config import get_default_db
from src.orm.exceptions import ModelError
from src.orm.relations.fields import ForeignKey, ManyToManyField
from src.orm.constraints import Index, CheckConstraint, UniqueConstraint


def setup_model(cls, *, table_name=None, db=None):
    if table_name:
        cls._table_name = table_name
    elif not hasattr(cls, "_table_name"):
        cls._table_name = cls.__name__.lower()

    cls._fields = {}
    cls._fk_fields = {}
    cls._m2m_fields = {}

    for name, attr in list(cls.__dict__.items()):
        if isinstance(attr, ManyToManyField):
            attr.contribute(cls, name)
            cls._m2m_fields[name] = attr
        elif isinstance(attr, ForeignKey):
            cls._fields[attr.fk_column] = attr
            cls._fk_fields[name] = attr
            attr._setup_reverse(cls)
        elif isinstance(attr, Field):
            cls._fields[name] = attr
            attr.__set_name__(cls, name)

    cls.objects = ModelManager(cls)

    if db is not None:
        cls._db = db
    elif not hasattr(cls, "_db"):
        default_db = get_default_db()
        if default_db is None:
            raise ModelError(
                f"Model '{cls.__name__}' must have a '_db' attribute "
                "or configure default db with configure()"
            )
        cls._db = default_db

    _collect_indexes(cls)
    _collect_constraints(cls)

    registry.register(cls)


def _collect_indexes(cls) -> None:
    raw = getattr(cls, "_indexes", None)
    if raw is not None:
        cls._indexes = raw
    else:
        cls._indexes = []

    seen = {i.name for i in cls._indexes if i.name}
    for name, field in cls._fields.items():
        if hasattr(field, "db_index") and field.db_index:
            idx_name = f"idx_{cls._table_name}_{name}"
            if idx_name not in seen:
                cls._indexes.append(Index(name, name=idx_name))
                seen.add(idx_name)


def _collect_constraints(cls) -> None:
    raw = getattr(cls, "_constraints", None)
    if raw is not None:
        cls._constraints = raw
    else:
        cls._constraints = []
