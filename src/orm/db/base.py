from abc import ABC, abstractmethod
from typing import Optional, List, Any
from src.orm.db.dialect import Dialect


class DatabaseAdapter(ABC):
    _dialect: Optional[Dialect] = None

    @abstractmethod
    def connect(self) -> None:
        pass

    @abstractmethod
    def execute(self, query: str, params: Optional[List[Any]] = None) -> Any:
        pass

    def _execute_no_commit(self, query: str, params: Optional[List[Any]] = None) -> Any:
        return self.execute(query, params)

    @abstractmethod
    def query(self, query: str, params: Optional[List[Any]] = None) -> Any:
        pass

    @abstractmethod
    def commit(self) -> None:
        pass

    @abstractmethod
    def rollback(self) -> None:
        pass

    @abstractmethod
    def close(self) -> None:
        pass

    @abstractmethod
    def get_dialect(self) -> Dialect:
        pass

    @property
    def param_style(self) -> str:
        return self.get_dialect().param_style

    # --- Transaction helpers ---

    def transaction(self):
        return TransactionContext(self)

    def begin(self) -> None:
        self._execute_no_commit("BEGIN")

    def savepoint(self, name: str) -> None:
        q = self.get_dialect().quote_identifier(name)
        self._execute_no_commit(f"SAVEPOINT {q}")

    def rollback_to_savepoint(self, name: str) -> None:
        q = self.get_dialect().quote_identifier(name)
        self._execute_no_commit(f"ROLLBACK TO SAVEPOINT {q}")

    def release_savepoint(self, name: str) -> None:
        q = self.get_dialect().quote_identifier(name)
        self._execute_no_commit(f"RELEASE SAVEPOINT {q}")

    def set_isolation_level(self, level: str) -> None:
        raise NotImplementedError(
            f"set_isolation_level not implemented for {self.get_dialect().name}"
        )

    def nested_transaction(self):
        return NestedTransactionContext(self)


class TransactionContext:
    def __init__(self, db: DatabaseAdapter):
        self.db = db
        self._active = False

    def __enter__(self):
        self.db.begin()
        self._active = True
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if not self._active:
            return False
        self._active = False
        if exc_type is None:
            self.db.commit()
        else:
            try:
                self.db.rollback()
            except Exception:
                pass
        return False


class NestedTransactionContext:
    def __init__(self, db: DatabaseAdapter):
        self.db = db
        self._name = None
        self._active = False

    def __enter__(self):
        import uuid
        self._name = f"sp_{uuid.uuid4().hex[:8]}"
        self.db.savepoint(self._name)
        self._active = True
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if not self._active:
            return False
        self._active = False
        if exc_type is None:
            self.db.release_savepoint(self._name)
        else:
            try:
                self.db.rollback_to_savepoint(self._name)
            except Exception:
                pass
        return False
