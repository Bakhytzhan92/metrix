"""
Генерация инвентарных номеров: {префикс компании}-{категория}-{000001}.
"""
from __future__ import annotations

import re

from django.db import transaction

from .models import Company, InventoryNumberSequence, WarehouseInventoryItem


def _company_prefix(company: Company) -> str:
    raw = (company.inventory_prefix or "").strip().upper()
    if raw:
        clean = re.sub(r"[^A-ZА-ЯЁ0-9]", "", raw)
        return (clean[:8] or "CMP")
    name = (company.name or "").strip().upper()
    letters = re.findall(r"[A-ZА-ЯЁ]", name)
    if len(letters) >= 3:
        return "".join(letters[:3])
    alnum = re.sub(r"[^A-ZА-ЯЁ0-9]", "", name)
    return (alnum[:3] or "CMP").ljust(3, "X")[:6]


def _category_seq_key(category: str) -> str:
    return {
        WarehouseInventoryItem.CATEGORY_TOOL: "TOOL",
        WarehouseInventoryItem.CATEGORY_EQUIPMENT: "EQP",
        WarehouseInventoryItem.CATEGORY_ELECTRIC: "EL",
        WarehouseInventoryItem.CATEGORY_OTHER: "INS",
    }.get(category, "INS")


@transaction.atomic
def allocate_inventory_number(company: Company, category: str) -> str:
    """Уникальный номер в рамках компании (через счётчик и constraint в БД)."""
    prefix = _company_prefix(company)
    seq_key = _category_seq_key(category)
    row, _ = InventoryNumberSequence.objects.select_for_update().get_or_create(
        company=company,
        key=seq_key,
        defaults={"last_value": 0},
    )
    row.last_value += 1
    row.save(update_fields=["last_value"])
    return f"{prefix}-{seq_key}-{row.last_value:06d}"
