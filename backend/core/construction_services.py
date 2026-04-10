"""Стройка: пересчёт факта/статусов по смете и журналу отчётов."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum

from .access_utils import get_company_user, is_company_owner
from .models import ConstructionWorkLog, ConstructionWorkPhoto, EstimateItem, ProjectAccess


def recalc_estimate_item_construction(item_id: int) -> None:
    """Сумма объёмов из журнала → факт; статус по плану, факту и срокам графика."""
    item = EstimateItem.objects.get(pk=item_id)
    agg = item.construction_logs.aggregate(s=Sum("volume"))
    total_vol = agg.get("s")
    if total_vol is None:
        total_vol = Decimal("0")
    else:
        total_vol = Decimal(str(total_vol))
    item.construction_actual_quantity = total_vol

    plan = item.quantity or Decimal("0")
    act = total_vol
    today = date.today()
    end = item.schedule_end

    if plan <= 0:
        status = EstimateItem.CONSTRUCTION_NOT_STARTED
    elif act >= plan:
        status = EstimateItem.CONSTRUCTION_COMPLETED
    elif end and end < today and act < plan:
        status = EstimateItem.CONSTRUCTION_OVERDUE
    elif act > Decimal("0"):
        status = EstimateItem.CONSTRUCTION_IN_PROGRESS
    else:
        status = EstimateItem.CONSTRUCTION_NOT_STARTED

    item.construction_exec_status = status
    item.save(
        update_fields=["construction_actual_quantity", "construction_exec_status"]
    )


def create_construction_log_with_photos(
    item: EstimateItem,
    user,
    work_date: date,
    volume: Decimal,
    comment: str,
    files: list,
) -> ConstructionWorkLog:
    with transaction.atomic():
        log = ConstructionWorkLog.objects.create(
            estimate_item=item,
            work_date=work_date,
            volume=volume,
            comment=comment or "",
            created_by=user,
        )
        for f in files:
            if f:
                ConstructionWorkPhoto.objects.create(work_log=log, image=f)
        recalc_estimate_item_construction(item.pk)
    return log


def construction_is_readonly(user, project) -> bool:
    """
    Наблюдатель проекта (клиент) — только просмотр.
    Владелец компании и без явной роли viewer — могут вносить отчёты.
    """
    company = project.company
    if is_company_owner(user, company):
        return False
    cu = get_company_user(user, company)
    if not cu:
        return False
    pa = ProjectAccess.objects.filter(company_user=cu, project=project).first()
    if pa and pa.role_in_project == ProjectAccess.ROLE_VIEWER:
        return True
    return False


def compute_construction_kpis(project) -> dict:
    """Прогресс по стоимости сметы, остаток, число просроченных позиций."""
    items = EstimateItem.objects.filter(section__project=project).only(
        "quantity",
        "total_cost",
        "construction_actual_quantity",
        "construction_exec_status",
    )
    total_cost_plan = Decimal("0")
    done_value = Decimal("0")
    overdue_count = 0

    for it in items:
        plan = it.quantity or Decimal("0")
        cost = it.total_cost or Decimal("0")
        if plan <= 0:
            continue
        total_cost_plan += cost
        act = it.construction_actual_quantity or Decimal("0")
        ratio = min(act / plan, Decimal("1"))
        done_value += cost * ratio
        if it.construction_exec_status == EstimateItem.CONSTRUCTION_OVERDUE:
            overdue_count += 1

    remaining = max(total_cost_plan - done_value, Decimal("0"))
    if total_cost_plan > 0:
        progress_pct = (done_value / total_cost_plan) * Decimal("100")
    else:
        progress_pct = Decimal("0")

    return {
        "progress_pct": progress_pct,
        "done_sum": done_value,
        "remaining_sum": remaining,
        "overdue_count": overdue_count,
        "planned_cost": total_cost_plan,
    }
