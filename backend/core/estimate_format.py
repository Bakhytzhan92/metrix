from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

SELL_PRICE_QUANT = Decimal("0.001")


def quantize_sell_price(value) -> Decimal:
    try:
        d = Decimal(str(value if value is not None else "0"))
    except (InvalidOperation, ValueError, TypeError):
        d = Decimal("0")
    return d.quantize(SELL_PRICE_QUANT, rounding=ROUND_HALF_UP)


def format_sell_price(value) -> str:
    """До 3 знаков после запятой, без лишних нулей (33773.375, 8000)."""
    s = format(quantize_sell_price(value), "f")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s if s not in ("", "-") else "0"
