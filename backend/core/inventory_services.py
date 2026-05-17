"""
Сервис инвентаря: склады, перемещения, выдача, ремонт, списание, логирование.
"""
from __future__ import annotations

from typing import Any

from django.db import transaction
from django.utils import timezone

from .models import Company, InventoryLog, InventoryTransfer, Warehouse, WarehouseInventoryItem

WRITTEN_OFF_WAREHOUSE_NAME = "Списано"


def material_names_casefold_for_company(company: Company) -> frozenset[str]:
    """Нормализованные названия материалов компании (для отделения от инвентаря оборудования)."""
    from .models import Material

    return frozenset(
        (n or "").strip().casefold()
        for n in Material.objects.filter(company=company).values_list("name", flat=True)
    )


def is_equipment_inventory_row(
    item: WarehouseInventoryItem,
    material_names_cf: frozenset[str],
) -> bool:
    """Позиция для досок/списков «инвентарь», не дубликат материала из справочника."""
    if getattr(item, "category", None) == "material":
        return False
    key = (item.name or "").strip().casefold()
    if key and key in material_names_cf:
        return False
    return True


def get_written_off_warehouse(company: Company) -> Warehouse:
    wh, _ = Warehouse.objects.get_or_create(
        company=company,
        name=WRITTEN_OFF_WAREHOUSE_NAME,
        defaults={"project": None, "is_deleted": False},
    )
    return wh


def log_inventory_action(
    item: WarehouseInventoryItem,
    action: str,
    user,
    description: str = "",
    details: dict[str, Any] | None = None,
) -> None:
    InventoryLog.objects.create(
        item=item,
        action=action,
        description=description or "",
        details=details or {},
        user=user,
    )


@transaction.atomic
def transfer_inventory_item(
    item: WarehouseInventoryItem,
    to_warehouse: Warehouse,
    user,
    comment: str = "",
) -> InventoryTransfer:
    from_warehouse = item.warehouse
    item.warehouse = to_warehouse
    item.save(update_fields=["warehouse", "updated_at"])
    transfer = InventoryTransfer.objects.create(
        item=item,
        from_warehouse=from_warehouse,
        to_warehouse=to_warehouse,
        user=user,
        date=timezone.now(),
        comment=comment or "",
    )
    log_inventory_action(
        item,
        InventoryLog.ACTION_MOVED,
        user,
        description=f"«{from_warehouse.name}» → «{to_warehouse.name}»"
        + (f". {comment}" if comment else ""),
        details={"comment": comment},
    )
    return transfer


@transaction.atomic
def set_inventory_status(
    item: WarehouseInventoryItem,
    new_status: str,
    user,
    available_from=None,
    description: str = "",
) -> None:
    old_status = item.status
    if available_from is not None:
        item.available_from = available_from
    if new_status == WarehouseInventoryItem.STATUS_WRITTEN_OFF:
        written_off_wh = get_written_off_warehouse(item.company)
        if item.warehouse_id != written_off_wh.id:
            transfer_inventory_item(item, written_off_wh, user, comment="Списание")
        item.status = new_status
        item.assigned_to = None
        item.issued_at = None
        item.return_due_at = None
        item.save(
            update_fields=[
                "status",
                "available_from",
                "assigned_to",
                "issued_at",
                "return_due_at",
                "updated_at",
            ]
        )
        if old_status != new_status:
            log_inventory_action(
                item,
                InventoryLog.ACTION_WRITEOFF,
                user,
                description=description or f"Списан (было: {old_status})",
            )
        return
    if new_status in (
        WarehouseInventoryItem.STATUS_FREE,
        WarehouseInventoryItem.STATUS_IN_USE,
    ):
        item.assigned_to = None
        item.issued_at = None
        item.return_due_at = None
    item.status = new_status
    item.save(update_fields=[
        "status",
        "available_from",
        "assigned_to",
        "issued_at",
        "return_due_at",
        "updated_at",
    ])
    if old_status != new_status:
        log_inventory_action(
            item,
            InventoryLog.ACTION_STATUS_CHANGED,
            user,
            description=description or f"Статус: {item.get_status_display()}",
            details={"from": old_status, "to": new_status},
        )


@transaction.atomic
def issue_inventory_to_user(
    item: WarehouseInventoryItem,
    to_user,
    acting_user,
    *,
    comment: str = "",
    return_due_at=None,
) -> None:
    item.status = WarehouseInventoryItem.STATUS_ISSUED
    item.assigned_to = to_user
    item.issued_at = timezone.now()
    item.return_due_at = return_due_at
    item.save(
        update_fields=[
            "status",
            "assigned_to",
            "issued_at",
            "return_due_at",
            "updated_at",
        ]
    )
    log_inventory_action(
        item,
        InventoryLog.ACTION_ISSUED,
        acting_user,
        description=comment
        or f"Выдан пользователю {to_user.get_username() if to_user else '—'}",
        details={
            "assigned_to_id": to_user.id if to_user else None,
            "return_due_at": str(return_due_at) if return_due_at else None,
            "comment": comment,
        },
    )


@transaction.atomic
def return_inventory_from_user(
    item: WarehouseInventoryItem,
    acting_user,
    *,
    comment: str = "",
    new_status: str = WarehouseInventoryItem.STATUS_FREE,
) -> None:
    prev_assignee = item.assigned_to_id
    item.status = new_status
    item.assigned_to = None
    item.issued_at = None
    item.return_due_at = None
    item.save(
        update_fields=[
            "status",
            "assigned_to",
            "issued_at",
            "return_due_at",
            "updated_at",
        ]
    )
    log_inventory_action(
        item,
        InventoryLog.ACTION_RETURNED,
        acting_user,
        description=comment or "Возврат от сотрудника",
        details={"previous_assignee_id": prev_assignee, "comment": comment},
    )


@transaction.atomic
def mark_inventory_repair(item: WarehouseInventoryItem, acting_user, *, comment: str = "") -> None:
    item.status = WarehouseInventoryItem.STATUS_REPAIR
    item.save(update_fields=["status", "updated_at"])
    log_inventory_action(
        item,
        InventoryLog.ACTION_REPAIR,
        acting_user,
        description=comment or "Передан на ремонт",
        details={"comment": comment},
    )


@transaction.atomic
def mark_inventory_lost(item: WarehouseInventoryItem, acting_user, *, comment: str = "") -> None:
    item.status = WarehouseInventoryItem.STATUS_LOST
    item.assigned_to = None
    item.issued_at = None
    item.save(update_fields=["status", "assigned_to", "issued_at", "updated_at"])
    log_inventory_action(
        item,
        InventoryLog.ACTION_LOST,
        acting_user,
        description=comment or "Потерян",
        details={"comment": comment},
    )
