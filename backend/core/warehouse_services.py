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
def apply_writeoff(
    *,
    material: Material,
    warehouse: Warehouse,
    quantity: Decimal,
    date,
    comment: str = "",
    project: Project | None = None,
):
    """Списание со склада (или списание на объект с project)."""
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
        movement_type=StockMovement.TYPE_OUTGOING if project else StockMovement.TYPE_WRITEOFF,
        quantity=quantity,
        price=price,
        date=date,
        comment=comment,
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
