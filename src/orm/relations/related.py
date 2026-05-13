from typing import Any, Optional
from src.orm.query import QuerySet


class RelatedManager:
    def __init__(self, fk_field: Any, rel_name: str) -> None:
        self.fk_field = fk_field
        self._rel_name = rel_name

    def __get__(self, instance: Any, owner: Any) -> Any:
        if instance is None:
            return self
        return _RelatedManagerInstance(self, instance)

    def _query(self, instance: Any) -> QuerySet:
        pk_name = getattr(instance, "_pk_field", None) or "id"
        return QuerySet(self.fk_field.owner).filter(
            **{self.fk_field.fk_column: getattr(instance, pk_name)}
        )


class _RelatedManagerInstance:
    def __init__(self, mgr: RelatedManager, instance: Any) -> None:
        self._mgr = mgr
        self._instance = instance

    def _cache_key(self) -> str:
        return f"_{self._mgr._rel_name}_cached"

    def all(self) -> list[Any]:
        cache_key = self._cache_key()
        cached = self._instance.__dict__.get(cache_key)
        if cached is not None:
            return cached
        results = self._mgr._query(self._instance).all()
        self._instance.__dict__[cache_key] = results
        return results

    def filter(self, **kwargs: Any) -> QuerySet:
        return self._mgr._query(self._instance).filter(**kwargs)

    def create(self, **kwargs: Any) -> Any:
        cache_key = self._cache_key()
        self._instance.__dict__.pop(cache_key, None)
        pk_name = getattr(self._instance, "_pk_field", None) or "id"
        kwargs[self._mgr.fk_field.fk_column] = getattr(self._instance, pk_name)
        return self._mgr.fk_field.owner.objects.create(**kwargs)

    def count(self) -> int:
        return self._mgr._query(self._instance).count()

    def exists(self) -> bool:
        return self._mgr._query(self._instance).exists()


class ManyRelatedManager:
    def __init__(self, m2m_field: Any) -> None:
        self.m2m_field = m2m_field

    def __get__(self, instance: Any, owner: Any) -> Any:
        if instance is None:
            return self
        return _ManyRelatedManagerInstance(self, instance)

    def _related_ids(self, instance: Any) -> list[Any]:
        pk_name = self.m2m_field._get_pk_name(self.m2m_field.owner)
        t1 = self.m2m_field.owner._table_name
        t2 = self.m2m_field.to._table_name
        fk_col = f"{t1}_id"
        target_col = f"{t2}_id"
        pk_value = getattr(instance, pk_name)

        cursor = self.m2m_field.to._db.query(
            f"SELECT {target_col} FROM {self.m2m_field.table_name} WHERE {fk_col} = ?",
            [pk_value],
        )
        rows = cursor.fetchall()
        return [row[target_col] if hasattr(row, "keys") else row[0] for row in rows]


class _ManyRelatedManagerInstance:
    def __init__(self, mgr: ManyRelatedManager, instance: Any) -> None:
        self._mgr = mgr
        self._instance = instance

    def _cache_key(self) -> str:
        return f"_{self._mgr.m2m_field.name}_cached"

    def all(self) -> list[Any]:
        cache_key = self._cache_key()
        cached = self._instance.__dict__.get(cache_key)
        if cached is not None:
            return cached
        ids = self._mgr._related_ids(self._instance)
        if not ids:
            self._instance.__dict__[cache_key] = []
            return []
        pk_name = self._mgr.m2m_field._get_pk_name(self._mgr.m2m_field.to)
        results = self._mgr.m2m_field.to.objects.filter(**{f"{pk_name}__in": ids}).all()
        self._instance.__dict__[cache_key] = results
        return results

    def add(self, *objects: Any) -> None:
        cache_key = self._cache_key()
        self._instance.__dict__.pop(cache_key, None)
        pk_name = getattr(self._instance, "_pk_field", None) or "id"
        t1 = self._mgr.m2m_field.owner._table_name
        t2 = self._mgr.m2m_field.to._table_name
        for obj in objects:
            self._mgr.m2m_field.to._db.execute(
                f"INSERT OR IGNORE INTO {self._mgr.m2m_field.table_name} ({t1}_id, {t2}_id) VALUES (?, ?)",
                [getattr(self._instance, pk_name), obj.pk],
            )

    def remove(self, *objects: Any) -> None:
        cache_key = self._cache_key()
        self._instance.__dict__.pop(cache_key, None)
        pk_name = getattr(self._instance, "_pk_field", None) or "id"
        t1 = self._mgr.m2m_field.owner._table_name
        t2 = self._mgr.m2m_field.to._table_name
        for obj in objects:
            self._mgr.m2m_field.to._db.execute(
                f"DELETE FROM {self._mgr.m2m_field.table_name} WHERE {t1}_id = ? AND {t2}_id = ?",
                [getattr(self._instance, pk_name), obj.pk],
            )

    def clear(self) -> None:
        cache_key = self._cache_key()
        self._instance.__dict__.pop(cache_key, None)
        pk_name = getattr(self._instance, "_pk_field", None) or "id"
        t1 = self._mgr.m2m_field.owner._table_name
        self._mgr.m2m_field.to._db.execute(
            f"DELETE FROM {self._mgr.m2m_field.table_name} WHERE {t1}_id = ?",
            [getattr(self._instance, pk_name)],
        )


class ManyToManyForwardManager:
    def __init__(self, m2m_field: Any, instance: Any) -> None:
        self._m2m = m2m_field
        self._instance = instance

    def _cache_key(self) -> str:
        return f"_{self._m2m.name}_cached"

    def _related_ids(self) -> list[Any]:
        pk_name = self._m2m._get_pk_name(self._m2m.owner)
        t1 = self._m2m.owner._table_name
        t2 = self._m2m.to._table_name
        pk_value = getattr(self._instance, pk_name)
        cursor = self._m2m.to._db.query(
            f"SELECT {t2}_id FROM {self._m2m.table_name} WHERE {t1}_id = ?",
            [pk_value],
        )
        rows = cursor.fetchall()
        return [row[f"{t2}_id"] if hasattr(row, "keys") else row[0] for row in rows]

    def all(self) -> list[Any]:
        cache_key = self._cache_key()
        cached = self._instance.__dict__.get(cache_key)
        if cached is not None:
            return cached
        ids = self._related_ids()
        if not ids:
            self._instance.__dict__[cache_key] = []
            return []
        pk_name = self._m2m._get_pk_name(self._m2m.to)
        results = self._m2m.to.objects.filter(**{f"{pk_name}__in": ids}).all()
        self._instance.__dict__[cache_key] = results
        return results

    def add(self, *objects: Any) -> None:
        cache_key = self._cache_key()
        self._instance.__dict__.pop(cache_key, None)
        pk_name = getattr(self._instance, "_pk_field", None) or "id"
        t1 = self._m2m.owner._table_name
        t2 = self._m2m.to._table_name
        for obj in objects:
            self._m2m.to._db.execute(
                f"INSERT OR IGNORE INTO {self._m2m.table_name} ({t1}_id, {t2}_id) VALUES (?, ?)",
                [getattr(self._instance, pk_name), obj.pk],
            )

    def remove(self, *objects: Any) -> None:
        cache_key = self._cache_key()
        self._instance.__dict__.pop(cache_key, None)
        pk_name = getattr(self._instance, "_pk_field", None) or "id"
        t1 = self._m2m.owner._table_name
        t2 = self._m2m.to._table_name
        for obj in objects:
            self._m2m.to._db.execute(
                f"DELETE FROM {self._m2m.table_name} WHERE {t1}_id = ? AND {t2}_id = ?",
                [getattr(self._instance, pk_name), obj.pk],
            )

    def clear(self) -> None:
        cache_key = self._cache_key()
        self._instance.__dict__.pop(cache_key, None)
        pk_name = getattr(self._instance, "_pk_field", None) or "id"
        t1 = self._m2m.owner._table_name
        self._m2m.to._db.execute(
            f"DELETE FROM {self._m2m.table_name} WHERE {t1}_id = ?",
            [getattr(self._instance, pk_name)],
        )
