from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


@register.filter
def qty_plain(value):
    """Число для поля «Кол-во»: без лишних нулей в дробной части; точка как разделитель, не запятая."""
    if value is None or value == "":
        return ""
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return str(value)
    s = format(d, "f")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s if s not in ("", "-") else "0"
