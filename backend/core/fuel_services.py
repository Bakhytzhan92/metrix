"""Операции ГСМ: остатки FuelStock и журнал FuelTransaction (отдельно от материалов)."""
from __future__ import annotations

from decimal import Decimal

from django.db import transaction

from .models import Company, EquipmentFuelLog, FuelStock, FuelTransaction, FuelType, Warehouse

DEFAULT_FUEL_TYPES: tuple[tuple[str, str, str], ...] = (
    ("ai92", "АИ-92", "л"),
    ("ai95", "АИ-95", "л"),
    ("diesel", "ДТ", "л"),
    ("gas", "Газ", "м³"),
    ("oil", "Масло", "л"),
)


def ensure_default_fuel_types(company: Company) -> None:
    existing = set(
        FuelType.objects.filter(company=company).values_list("code", flat=True)
    )
    for code, name, unit in DEFAULT_FUEL_TYPES:
        if code not in existing:
            FuelType.objects.create(
                company=company, code=code, name=name, unit=unit
            )


def _assert_same_company(warehouse: Warehouse, fuel_type: FuelType) -> None:
    if warehouse.company_id != fuel_type.company_id:
        raise ValueError("Склад и вид топлива должны принадлежать одной компании.")


@transaction.atomic
def apply_fuel_incoming(
    *,
    fuel_type: FuelType,
    warehouse: Warehouse,
    quantity: Decimal,
    price: Decimal,
    date,
    comment: str = "",
    supplier: str = "",
    document_number: str = "",
    user=None,
) -> FuelTransaction:
    _assert_same_company(warehouse, fuel_type)
    if quantity is None or quantity <= 0:
        raise ValueError("Количество должно быть больше нуля.")
    tx = FuelTransaction.objects.create(
        fuel_type=fuel_type,
        warehouse=warehouse,
        movement_type=FuelTransaction.TYPE_INCOMING,
        quantity=quantity,
        price=price,
        date=date,
        comment=(comment or "")[:500],
        supplier=(supplier or "")[:255],
        document_number=(document_number or "")[:120],
        user=user,
    )
    stock, _ = FuelStock.objects.select_for_update().get_or_create(
        warehouse=warehouse,
        fuel_type=fuel_type,
        defaults={"quantity": Decimal("0"), "price_avg": Decimal("0")},
    )
    new_qty = stock.quantity + quantity
    new_total = stock.quantity * stock.price_avg + quantity * price
    stock.price_avg = new_total / new_qty if new_qty else Decimal("0")
    stock.quantity = new_qty
    stock.save()
    return tx


@transaction.atomic
def apply_fuel_issue(
    *,
    fuel_type: FuelType,
    warehouse: Warehouse,
    quantity: Decimal,
    date,
    price: Decimal | None = None,
    comment: str = "",
    recipient_type: str = "",
    issued_to_name: str = "",
    equipment_name: str = "",
    driver_name: str = "",
    equipment=None,
    target_project=None,
    contractor_name: str = "",
    user=None,
) -> FuelTransaction:
    _assert_same_company(warehouse, fuel_type)
    if quantity is None or quantity <= 0:
        raise ValueError("Количество должно быть больше нуля.")
    stock = FuelStock.objects.select_for_update().get(
        warehouse=warehouse, fuel_type=fuel_type
    )
    if stock.quantity < quantity:
        raise ValueError(
            f"Недостаточно «{fuel_type.name}» на складе «{warehouse.name}». Остаток: {stock.quantity} {fuel_type.unit}"
        )
    unit_price = price if price is not None else stock.price_avg
    tx = FuelTransaction.objects.create(
        fuel_type=fuel_type,
        warehouse=warehouse,
        movement_type=FuelTransaction.TYPE_ISSUE,
        quantity=quantity,
        price=unit_price or Decimal("0"),
        date=date,
        comment=(comment or "")[:500],
        recipient_type=(recipient_type or "")[:20],
        issued_to_name=(issued_to_name or "")[:255],
        driver_name=(driver_name or "")[:255],
        equipment_name=(equipment_name or "")[:255],
        equipment=equipment,
        target_project=target_project,
        contractor_name=(contractor_name or "")[:255],
        user=user,
    )
    stock.quantity -= quantity
    stock.save()
    if equipment is not None:
        EquipmentFuelLog.objects.create(equipment=equipment, transaction=tx)
    return tx


@transaction.atomic
def apply_fuel_writeoff(
    *,
    fuel_type: FuelType,
    warehouse: Warehouse,
    quantity: Decimal,
    date,
    writeoff_reason: str,
    comment: str = "",
    user=None,
) -> FuelTransaction:
    _assert_same_company(warehouse, fuel_type)
    if quantity is None or quantity <= 0:
        raise ValueError("Количество должно быть больше нуля.")
    reasons = dict(FuelTransaction.WRITEOFF_REASON_CHOICES)
    if writeoff_reason not in reasons:
        writeoff_reason = FuelTransaction.WO_MACHINERY
    stock = FuelStock.objects.select_for_update().get(
        warehouse=warehouse, fuel_type=fuel_type
    )
    if stock.quantity < quantity:
        raise ValueError(
            f"Недостаточно «{fuel_type.name}» на складе «{warehouse.name}». Остаток: {stock.quantity} {fuel_type.unit}"
        )
    unit_price = stock.price_avg
    tx = FuelTransaction.objects.create(
        fuel_type=fuel_type,
        warehouse=warehouse,
        movement_type=FuelTransaction.TYPE_WRITEOFF,
        quantity=quantity,
        price=unit_price or Decimal("0"),
        date=date,
        comment=(comment or "")[:500],
        writeoff_reason=writeoff_reason,
        user=user,
    )
    stock.quantity -= quantity
    stock.save()
    return tx
