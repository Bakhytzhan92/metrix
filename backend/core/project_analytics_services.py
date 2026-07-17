"""KPI аналитики проекта: смета + финансы + снабжение."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Sum

from . import finance_project_services
from . import supply_services
from .models import EstimateItem


def _q2(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _as_decimal(v) -> Decimal:
    if v is None:
        return Decimal("0")
    if isinstance(v, Decimal):
        return v
    return Decimal(str(v))


def _estimate_totals(project) -> dict:
    agg = EstimateItem.objects.filter(
        section__project=project,
        is_subsection_header=False,
    ).aggregate(
        cost=Sum("total_cost"),
        price=Sum("total_price"),
    )
    cost = _as_decimal(agg.get("cost"))
    price = _as_decimal(agg.get("price"))
    markup = price - cost
    vat_amt = _q2(price * Decimal("0.16")) if project.estimate_vat_enabled else Decimal("0")
    client_total = _q2(price * Decimal("1.16")) if project.estimate_vat_enabled else price
    return {
        "total_cost": cost,
        "total_price": price,
        "markup": markup,
        "vat_amount": vat_amt,
        "client_total": client_total,
    }


def _margin_pct(profit: Decimal, revenue: Decimal) -> Decimal | None:
    if revenue <= 0:
        return None
    return _q2(profit / revenue * Decimal("100"))


def _estimate_by_type_chart(project) -> list[dict]:
    type_labels = dict(EstimateItem.TYPE_CHOICES)
    colors = {
        EstimateItem.TYPE_MATERIAL: "#f59e0b",
        EstimateItem.TYPE_LABOR: "#6d5ef8",
        EstimateItem.TYPE_EQUIPMENT: "#0ea5e9",
        EstimateItem.TYPE_DELIVERY: "#64748b",
    }
    rows = (
        EstimateItem.objects.filter(
            section__project=project,
            is_subsection_header=False,
        )
        .values("type")
        .annotate(amount=Sum("total_price"))
        .order_by("type")
    )
    segments: list[dict] = []
    for row in rows:
        amt = _as_decimal(row["amount"])
        if amt <= 0:
            continue
        t = row["type"]
        segments.append(
            {
                "label": type_labels.get(t, t),
                "value": float(amt),
                "color": colors.get(t, "#94a3b8"),
            }
        )
    return segments


def _plan_structure_chart(cost_plan: Decimal, plan_profit: Decimal) -> list[dict]:
    segments: list[dict] = []
    if cost_plan > 0:
        segments.append(
            {
                "label": "Себестоимость",
                "value": float(cost_plan),
                "color": "#fb923c",
            }
        )
    if plan_profit > 0:
        segments.append(
            {
                "label": "Прибыль",
                "value": float(plan_profit),
                "color": "#22c55e",
            }
        )
    elif plan_profit < 0:
        segments.append(
            {
                "label": "Убыток",
                "value": float(abs(plan_profit)),
                "color": "#ef4444",
            }
        )
    return segments


def _costs_chart(expense: Decimal, upcoming: Decimal) -> list[dict]:
    segments: list[dict] = []
    if expense > 0:
        segments.append(
            {
                "label": "Текущие расходы",
                "value": float(expense),
                "color": "#ef4444",
            }
        )
    if upcoming > 0:
        segments.append(
            {
                "label": "Предстоящие",
                "value": float(upcoming),
                "color": "#f97316",
            }
        )
    return segments


def compute_project_analytics(project) -> dict:
    """Сводные показатели для вкладки «Аналитика» проекта."""
    est = _estimate_totals(project)
    fin = finance_project_services.project_finance_kpis(project)
    sup = supply_services.compute_project_supply_kpis(project)

    revenue_plan = est["total_price"]
    cost_plan = est["total_cost"]
    plan_profit = est["markup"]
    plan_margin = _margin_pct(plan_profit, revenue_plan)

    income = _as_decimal(fin["income"])
    expense = _as_decimal(fin["expense"])
    orders_to_pay = _as_decimal(fin["orders_to_pay"])
    works_to_pay = _as_decimal(fin["works_to_pay"])
    upcoming_costs = orders_to_pay + works_to_pay

    forecast_profit = revenue_plan - expense - upcoming_costs
    forecast_margin = _margin_pct(forecast_profit, revenue_plan)

    revenue_upcoming = max(Decimal("0"), revenue_plan - income)
    supply_savings = _as_decimal(sup["savings"])

    charts = {
        "estimate_types": _estimate_by_type_chart(project),
        "plan_structure": _plan_structure_chart(cost_plan, plan_profit),
        "costs": _costs_chart(expense, upcoming_costs),
    }

    return {
        "estimate_total": est["client_total"],
        "estimate_total_price": revenue_plan,
        "cost_plan": cost_plan,
        "plan_profit": plan_profit,
        "plan_margin_pct": plan_margin,
        "forecast_profit": forecast_profit,
        "forecast_margin_pct": forecast_margin,
        "balance_savings": supply_savings,
        "balance_income_expense": income - expense,
        "revenue_current": income,
        "revenue_upcoming": revenue_upcoming,
        "revenue_diff": revenue_upcoming,
        "cost_current": expense,
        "cost_upcoming": upcoming_costs,
        "cost_savings": supply_savings,
        "vat_enabled": project.estimate_vat_enabled,
        "charts": charts,
    }
