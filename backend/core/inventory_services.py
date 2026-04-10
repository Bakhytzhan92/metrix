"""
Сервис инвентаря: получение склада «Списано», перемещение, смена статуса, логирование.
"""
from django.db import transaction

from .models import Company, Warehouse, WarehouseInventoryItem, InventoryTransfer, InventoryLog


WRITTEN_OFF_WAREHOUSE_NAME = "Списано"


def get_written_off_warehouse(company: Company) -> Warehouse:
    """Возвращает склад «Списано» для компании (создаёт при необходимости)."""
    wh, _ = Warehouse.objects.get_or_create(
        company=company,
        name=WRITTEN_OFF_WAREHOUSE_NAME,
        defaults={"project": None, "is_deleted": False},
    )
    return wh


def log_inventory_action(item: WarehouseInventoryItem, action: str, user, description: str = ""):
    """Записать действие в историю инвентаря."""
    InventoryLog.objects.create(
        item=item,
        action=action,
        description=description or "",
        user=user,
    )


@transaction.atomic
def transfer_inventory_item(
    item: WarehouseInventoryItem,
    to_warehouse: Warehouse,
    user,
) -> InventoryTransfer:
    """Переместить единицу инвентаря на другой склад. Создаёт запись перемещения и лог."""
    from_warehouse = item.warehouse
    item.warehouse = to_warehouse
    item.save(update_fields=["warehouse", "updated_at"])
    transfer = InventoryTransfer.objects.create(
        item=item,
        from_warehouse=from_warehouse,
        to_warehouse=to_warehouse,
        user=user,
    )
    from django.utils import timezone
    transfer.date = timezone.now()
    transfer.save(update_fields=["date"])
    log_inventory_action(
        item,
        InventoryLog.ACTION_MOVED,
        user,
        description=f"Со склада «{from_warehouse.name}» на склад «{to_warehouse.name}»",
    )
    return transfer


@transaction.atomic
def set_inventory_status(
    item: WarehouseInventoryItem,
    new_status: str,
    user,
    available_from=None,
) -> None:
    """Обновить статус инвентаря. При WRITTEN_OFF перемещает на склад «Списано»."""
    old_status = item.status
    if available_from is not None:
        item.available_from = available_from
    if new_status == WarehouseInventoryItem.STATUS_WRITTEN_OFF:
        written_off_wh = get_written_off_warehouse(item.company)
        if item.warehouse_id != written_off_wh.id:
            transfer_inventory_item(item, written_off_wh, user)
        item.status = new_status
        item.save(update_fields=["status", "available_from", "updated_at"])
        if old_status != new_status:
            log_inventory_action(
                item,
                InventoryLog.ACTION_STATUS_CHANGED,
                user,
                description=f"Статус: {item.get_status_display()}",
            )
        return
    item.status = new_status
    item.save(update_fields=["status", "available_from", "updated_at"])
    if old_status != new_status:
        log_inventory_action(
            item,
            InventoryLog.ACTION_STATUS_CHANGED,
            user,
            description=f"Статус: {item.get_status_display()}",
        )
