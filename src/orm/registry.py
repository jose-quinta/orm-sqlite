from typing import Dict, Type

class ModelRegistry:
  def __init__(self):
    self._models: Dict[str, Type] = {}

  def register(self, model: Type) -> None:
    if model.__name__ in self._models:
      if self._models[model.__name__] is model:
        return
      raise ValueError(f"Model '{model.__name__}' already registered")
    self._models[model.__name__] = model

  def get(self, name: str) -> Type:
    if name not in self._models:
      raise KeyError(f"Model '{name}' not found in registry")
    return self._models[name]

  def get_all(self) -> Dict[str, Type]:
    return self._models.copy()

  def unregister(self, name: str) -> None:
    if name in self._models:
      del self._models[name]

registry = ModelRegistry()
