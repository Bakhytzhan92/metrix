"""
Сервис операций склада: создание StockMovement и обновление Stock в atomic().
"""
from decimal import Decimal

from django.db import transaction

from .models import Material, Stock, StockMovement, Warehouse, Project


@transaction.atomic
def apply_incoming(
    *,
    material: Material,
    warehouse: Warehouse,
    quantity: Decimal,
    price: Decimal,
    date,
    comment: str = "",
    supplier: str = "",
    user=None,
):
    """Поступление на склад: создаём движение, увеличиваем остаток, пересчитываем среднюю цену."""
    movement = StockMovement.objects.create(
        material=material,
        warehouse_from=None,
        warehouse_to=warehouse,
        project=None,
        movement_type=StockMovement.TYPE_INCOMING,
        quantity=quantity,
        price=price,
        date=date,
        comment=comment,
        supplier=(supplier or "")[:255],
        user=user,
        writeoff_reason="",
    )
    stock, _ = Stock.objects.select_for_update().get_or_create(
        warehouse=warehouse,
        material=material,
        defaults={"quantity": 0, "price_avg": 0},
    )
    new_qty = stock.quantity + quantity
    new_total = stock.quantity * stock.price_avg + quantity * price
    stock.price_avg = new_total / new_qty if new_qty else Decimal("0")
    stock.quantity = new_qty
    stock.save()
    return movement


@transaction.atomic
def apply_outgoing_consumption(
    *,
    material: Material,
    warehouse: Warehouse,
    quantity: Decimal,
    date,
    project: Project,
    schedule_phase=None,
    comment: str = "",
    user=None,
):
    """Расход материала на объект (уменьшение остатка, история)."""
    stock = Stock.objects.select_for_update().get(
        warehouse=warehouse, material=material
    )
    if stock.quantity < quantity:
        raise ValueError(
            f"Недостаточно на складе «{warehouse.name}». Остаток: {stock.quantity} {material.unit}"
        )
    price = stock.price_avg
    movement = StockMovement.objects.create(
        material=material,
        warehouse_from=warehouse,
        warehouse_to=None,
        project=project,
        schedule_phase=schedule_phase,
        movement_type=StockMovement.TYPE_OUTGOING,
        quantity=quantity,
        price=price,
        date=date,
        comment=comment,
        user=user,
        writeoff_reason="",
        supplier="",
    )
    stock.quantity -= quantity
    stock.save()
    return movement


@transaction.atomic
def apply_writeoff(
    *,
    material: Material,
    warehouse: Warehouse,
    quantity: Decimal,
    date,
    comment: str = "",
    project: Project | None = None,
    writeoff_reason: str = "",
    user=None,
):
    """Списание со склада (расход на объект с project) или административное списание с причиной."""
    stock = Stock.objects.select_for_update().get(
        warehouse=warehouse, material=material
    )
    if stock.quantity < quantity:
        raise ValueError(
            f"Недостаточно на складе «{warehouse.name}». Остаток: {stock.quantity} {material.unit}"
        )
    price = stock.price_avg
    if project:
        mtype = StockMovement.TYPE_OUTGOING
        reason = ""
    else:
        mtype = StockMovement.TYPE_WRITEOFF
        reason = (writeoff_reason or StockMovement.REASON_USED)[:20]
    movement = StockMovement.objects.create(
        material=material,
        warehouse_from=warehouse,
        warehouse_to=None,
        project=project,
        movement_type=mtype,
        quantity=quantity,
        price=price,
        date=date,
        comment=comment,
        writeoff_reason=reason,
        user=user,
        supplier="",
    )
    stock.quantity -= quantity
    stock.save()
    return movement


@transaction.atomic
def apply_transfer(
    *,
    material: Material,
    warehouse_from: Warehouse,
    warehouse_to: Warehouse,
    quantity: Decimal,
    date,
    comment: str = "",
    user=None,
):
    """Перемещение между складами."""
    if warehouse_from.id == warehouse_to.id:
        raise ValueError("Склады должны различаться.")
    out_stock = Stock.objects.select_for_update().get(
        warehouse=warehouse_from, material=material
    )
    if out_stock.quantity < quantity:
        raise ValueError(
            f"Недостаточно на складе «{warehouse_from.name}». Остаток: {out_stock.quantity}"
        )
    price = out_stock.price_avg
    movement = StockMovement.objects.create(
        material=material,
        warehouse_from=warehouse_from,
        warehouse_to=warehouse_to,
        project=None,
        movement_type=StockMovement.TYPE_TRANSFER,
        quantity=quantity,
        price=price,
        date=date,
        comment=comment,
        user=user,
        writeoff_reason="",
        supplier="",
    )
    out_stock.quantity -= quantity
    out_stock.save()
    in_stock, _ = Stock.objects.select_for_update().get_or_create(
        warehouse=warehouse_to,
        material=material,
        defaults={"quantity": 0, "price_avg": 0},
    )
    new_qty = in_stock.quantity + quantity
    new_total = in_stock.quantity * in_stock.price_avg + quantity * price
    in_stock.price_avg = new_total / new_qty if new_qty else Decimal("0")
    in_stock.quantity = new_qty
    in_stock.save()
    return movement
