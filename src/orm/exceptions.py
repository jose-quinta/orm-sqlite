class ORMError(Exception):
  pass

class ModelError(ORMError):
  pass

class FieldError(ORMError):
  pass

class QueryError(ORMError):
  pass

class DoesNotExist(ORMError):
  pass
