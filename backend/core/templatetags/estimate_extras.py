import re
from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()

# Шифр норм в начале: 1101-0104-0201, 1137-0401-0203, иногда с хвостом '12'… из PDF
_RE_LEADING_NORM_CODE = re.compile(
    r"^(?:[0-9]+-[0-9]+-[0-9]+"
    r"(?:'[0-9+,\s.]*'[0-9'+\s.]*)*)\s+",
    re.IGNORECASE,
)


@register.filter
def strip_norm_code(
    value,
) -> str:
    """Убирает ведущий шифр норм (группы-цифр-через-дефис) из наименования."""
    s = (value or "").strip()
    for _ in range(4):
        m = _RE_LEADING_NORM_CODE.match(
            s
        )
        if not m:
            break
        s2 = s[
            m.end() :
        ].lstrip()
        if s2 == s:
            break
        s = s2
    return s


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


@register.simple_tag
def estimate_kind_cost_totals(sections):
    """
    Суммы себестоимости по типам позиций (материалы / работы) для KPI на странице сметы.
    Только отображение; источник — уже переданный в шаблон queryset разделов с prefetch items.
    """
    mat = Decimal("0")
    work = Decimal("0")
    for sec in sections:
        for item in sec.items.all():
            c = item.total_cost or Decimal("0")
            if not isinstance(c, Decimal):
                c = Decimal(str(c))
            if item.type == "material":
                mat += c
            elif item.type == "labor":
                work += c
    return {"materials": mat, "works": work}
