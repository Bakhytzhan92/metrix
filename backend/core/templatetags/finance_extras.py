"""Форматирование сумм в шаблонах финансов."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


def _format_amount(value, decimals: int = 2) -> str:
    try:
        number = Decimal(str(value).replace(",", ".").replace(" ", ""))
    except (InvalidOperation, TypeError, ValueError):
        return str(value)
    sign = "-" if number < 0 else ""
    number = abs(number)
    text = f"{number:.{decimals}f}"
    int_part, _, frac_part = text.partition(".")
    chunks = []
    while int_part:
        chunks.append(int_part[-3:])
        int_part = int_part[:-3]
    grouped = " ".join(reversed(chunks))
    if decimals > 0:
        return f"{sign}{grouped},{frac_part}"
    return f"{sign}{grouped}"


@register.filter
def money(value, decimals=2) -> str:
    """124644444 -> 124 644 444,00"""
    try:
        dec = int(decimals)
    except (TypeError, ValueError):
        dec = 2
    return _format_amount(value, dec)
