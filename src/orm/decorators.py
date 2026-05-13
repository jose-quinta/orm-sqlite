from src.orm._methods import init_model, save, delete, create_table, drop_table, repr_model, get_pk, set_pk
from src.orm.setup import setup_model
from src.orm.base import Model


def model(cls=None, *, table_name=None, db=None):
    def decorator(cls):
        if Model not in cls.__mro__:
            setup_model(cls, table_name=table_name, db=db)
            cls.save = save
            cls.delete = delete
            cls.create_table = classmethod(create_table)
            cls.drop_table = classmethod(drop_table)
            cls.__init__ = init_model
            cls.__repr__ = repr_model
            cls.pk = property(get_pk, set_pk)
        else:
            if table_name:
                cls._table_name = table_name
            if db:
                cls._db = db
        return cls

    if cls is None:
        return decorator
    return decorator(cls)
