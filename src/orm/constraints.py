from typing import Optional


class Index:
    def __init__(
        self,
        *fields: str,
        name: Optional[str] = None,
        unique: bool = False,
    ) -> None:
        self.fields = list(fields)
        self._name = name
        self.unique = unique

    @property
    def name(self) -> str:
        return self._name

    @name.setter
    def name(self, value: Optional[str]) -> None:
        self._name = value


class CheckConstraint:
    def __init__(
        self,
        condition: str,
        name: Optional[str] = None,
    ) -> None:
        self.condition = condition
        self.name = name


class UniqueConstraint:
    def __init__(
        self,
        *fields: str,
        name: Optional[str] = None,
    ) -> None:
        self.fields = list(fields)
        self.name = name
