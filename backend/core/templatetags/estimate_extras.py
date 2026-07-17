import re
from decimal import Decimal, InvalidOperation

from django import template

from core.estimate_format import format_sell_price

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


@register.filter
def sell_price_plain(value):
    """Цена заказчика за ед.: до 3 знаков после запятой."""
    if value is None or value == "":
        return ""
    return format_sell_price(value)


@register.simple_tag
def estimate_section_position_count(items) -> int:
    """Число позиций в разделе (без подзаголовков PDF)."""
    return sum(
        1 for it in items if not getattr(it, "is_subsection_header", False)
    )


@register.simple_tag
def estimate_item_row_no(item, items) -> str:
    """№ строки внутри раздела: pdf_pos_no при импорте Excel, иначе локальный счётчик."""
    pn = (getattr(item, "pdf_pos_no", None) or "").strip()
    if pn:
        return pn
    n = 0
    for it in items:
        if getattr(it, "is_subsection_header", False):
            continue
        n += 1
        if it.pk == item.pk:
            return str(n)
    return ""


@register.filter
def estimate_cyrillic_name(value) -> str:
    """Убирает английский дубляж в наименовании (разделы и позиции сметы)."""
    from core.services.excel_estimate_parser import normalize_estimate_name

    return normalize_estimate_name(value or "")


@register.filter
def estimate_section_header_class(style: str) -> str:
    """CSS-классы заголовка раздела по стилю из Excel."""
    s = (style or "").strip()
    if s == "red":
        return "bg-red-100/95 text-red-950"
    if s == "bordeaux":
        return "bg-red-200/90 text-red-950"
    if s == "gold":
        return "bg-amber-100/95 text-amber-950"
    return "bg-sky-100/95 text-slate-900"


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
            if item.is_subsection_header:
                continue
            c = item.total_cost or Decimal("0")
            if not isinstance(c, Decimal):
                c = Decimal(str(c))
            if item.type == "material":
                mat += c
            elif item.type == "labor":
                work += c
    return {"materials": mat, "works": work}
