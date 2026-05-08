from src.orm.fields import (
    PrimaryKeyField,
    CharField,
    IntegerField,
    FloatField,
    BooleanField,
    DateTimeField,
    TextField,
)


def _field(field_class, **default_kwargs):
    def decorator(fn=None, /, **kwargs):
        merged = {**default_kwargs, **kwargs}
        return field_class(**merged)

    return decorator


primary_key = _field(PrimaryKeyField)
char_field = _field(CharField, max_length=255)
integer_field = _field(IntegerField)
float_field = _field(FloatField)
boolean_field = _field(BooleanField)
datetime_field = _field(DateTimeField)
text_field = _field(TextField)
