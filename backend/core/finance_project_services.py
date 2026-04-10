"""KPI и суммарные показатели финансов проекта (раздел проекта «Финансы»)."""

from __future__ import annotations

from decimal import Decimal

from django.db.models import Sum

from .models import FinanceOperation, SupplyOrder, WorkAct


def project_finance_kpis(project) -> dict:
    """Доходы, расходы, остаток к оплате по заказам снабжения и актам."""
    ops = FinanceOperation.objects.filter(project=project)
    income = ops.filter(type=FinanceOperation.TYPE_INCOME).aggregate(
        s=Sum("amount")
    ).get("s") or Decimal("0")
    expense = ops.filter(type=FinanceOperation.TYPE_EXPENSE).aggregate(
        s=Sum("amount")
    ).get("s") or Decimal("0")

    supply_queue = SupplyOrder.objects.filter(
        project=project,
        payment_status__in=(
            SupplyOrder.PAYMENT_AWAITING,
            SupplyOrder.PAYMENT_PARTIAL,
        ),
    )
    orders_to_pay = Decimal("0")
    for o in supply_queue:
        orders_to_pay += o.remaining_amount

    acts_queue = WorkAct.objects.filter(
        project=project,
        payment_status__in=(
            WorkAct.PAYMENT_AWAITING,
            WorkAct.PAYMENT_PARTIAL,
        ),
    )
    works_to_pay = Decimal("0")
    for a in acts_queue:
        works_to_pay += a.remaining_amount

    return {
        "income": income,
        "expense": expense,
        "orders_to_pay": orders_to_pay,
        "works_to_pay": works_to_pay,
    }


def operation_basis_label(op: FinanceOperation) -> str:
    if op.basis == FinanceOperation.BASIS_SUPPLY_ORDER and op.supply_order_id:
        return "Заказ"
    if op.basis == FinanceOperation.BASIS_WORK_ACT and op.work_act_id:
        return "Акт"
    if op.basis == FinanceOperation.BASIS_ESTIMATE:
        return "Смета"
    return "—"
