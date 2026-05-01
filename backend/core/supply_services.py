"""Снабжение проекта: KPI, ресурс из позиции сметы."""

from __future__ import annotations

from decimal import Decimal

from django.db.models import Sum

from .models import EstimateItem, Resource, SupplyOrderItem, SupplyRequest


def _as_decimal(v) -> Decimal:
    if v is None:
        return Decimal("0")
    if isinstance(v, Decimal):
        return v
    return Decimal(str(v))


def estimate_budget_total(project) -> Decimal:
    """Бюджет по смете (сумма total_price позиций)."""
    agg = EstimateItem.objects.filter(section__project=project).aggregate(
        p=Sum("total_price")
    )
    return _as_decimal(agg.get("p"))


def get_or_create_resource_for_estimate_item(company, item: EstimateItem) -> Resource:
    """Справочник ресурсов для заявки из позиции сметы."""
    type_map = {
        EstimateItem.TYPE_MATERIAL: Resource.TYPE_MATERIAL,
        EstimateItem.TYPE_LABOR: Resource.TYPE_LABOR,
        EstimateItem.TYPE_EQUIPMENT: Resource.TYPE_EQUIPMENT,
        EstimateItem.TYPE_DELIVERY: Resource.TYPE_SERVICE,
    }
    rtype = type_map.get(item.type, Resource.TYPE_MATERIAL)
    name = (item.name or "").strip() or "Без названия"
    unit = (item.unit or "шт.")[:50]
    found = Resource.objects.filter(
        company=company, name=name[:255], type=rtype, unit=unit
    ).first()
    if found:
        return found
    return Resource.objects.create(
        company=company,
        name=name[:255],
        type=rtype,
        unit=unit,
    )


def purchased_qty_by_estimate_item(project) -> dict[int, Decimal]:
    """
    Накопленное количество «закуплено» по позиции сметы: сумма quantity_received
    по заявкам; если факт закупки не внесён, но есть заказ — берётся кол-во из заказа.
    """
    from collections import defaultdict

    out: dict[int, Decimal] = defaultdict(lambda: Decimal("0"))
    qs = (
        SupplyRequest.objects.filter(project=project, estimate_item_id__isnull=False)
        .exclude(status=SupplyRequest.STATUS_CANCELLED)
        .select_related("order_item")
    )
    for sr in qs:
        eid = sr.estimate_item_id
        if eid is None:
            continue
        q = _as_decimal(sr.quantity_received)
        if q <= 0:
            oi = getattr(sr, "order_item", None)
            if oi:
                q = _as_decimal(oi.quantity)
        out[eid] += q
    return dict(out)


def compute_project_supply_kpis(project) -> dict:
    """
    KPI для шапки снабжения проекта (как в Gectaro, упрощённо):
    бюджет, закуплено по плану / сверх плана, осталось, экономия.
    """
    budget = estimate_budget_total(project)

    plan_agg = (
        SupplyRequest.objects.filter(project=project)
        .exclude(status=SupplyRequest.STATUS_CANCELLED)
        .aggregate(s=Sum("total_plan"))
    )
    total_plan = _as_decimal(plan_agg.get("s"))

    fact_agg = SupplyOrderItem.objects.filter(request__project=project).aggregate(
        s=Sum("total_fact")
    )
    total_fact = _as_decimal(fact_agg.get("s"))

    purchased_on_plan = min(total_fact, total_plan)
    purchased_over = max(Decimal("0"), total_fact - total_plan)
    remaining = max(Decimal("0"), budget - total_fact)
    savings = max(Decimal("0"), total_plan - total_fact)

    return {
        "budget": budget,
        "purchased_on_plan": purchased_on_plan,
        "purchased_over": purchased_over,
        "remaining": remaining,
        "savings": savings,
        "total_plan": total_plan,
        "total_fact": total_fact,
    }
