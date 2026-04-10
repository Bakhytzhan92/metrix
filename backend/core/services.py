from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Iterable

from django.db.models import Case, DecimalField, F, Sum, Value, When
from django.db.models.functions import TruncMonth

from .models import FinanceCategory, FinanceOperation, Project, SupplyRequest, WarehouseOperation


@dataclass(frozen=True)
class MonthlyReportLine:
    key: str
    label: str
    months: list[date]
    values: dict[date, Decimal]

    @property
    def total(self) -> Decimal:
        return sum(self.values.get(m, Decimal("0")) for m in self.months)


def month_starts(date_from: date, date_to: date) -> list[date]:
    """Список первых чисел месяцев в диапазоне [date_from..date_to]."""
    if date_from > date_to:
        date_from, date_to = date_to, date_from
    cur = date(date_from.year, date_from.month, 1)
    end = date(date_to.year, date_to.month, 1)
    out: list[date] = []
    while cur <= end:
        out.append(cur)
        if cur.month == 12:
            cur = date(cur.year + 1, 1, 1)
        else:
            cur = date(cur.year, cur.month + 1, 1)
    return out


def default_pnl_bucket(op_type: str, pnl_group: str | None) -> str:
    """
    Привязка FinanceOperation к строкам P&L.
    Если pnl_group у статьи не задан — применяем дефолты:
    - доходы: выручка
    - расходы: переменные расходы
    """
    pnl_group = (pnl_group or "").strip()
    if op_type == FinanceOperation.TYPE_INCOME:
        return FinanceCategory.PNL_OTHER_INCOME if pnl_group == FinanceCategory.PNL_OTHER_INCOME else FinanceCategory.PNL_REVENUE
    if op_type == FinanceOperation.TYPE_EXPENSE:
        return pnl_group or FinanceCategory.PNL_VARIABLE_EXPENSE
    return "ignore"


def build_pnl(company, date_from: date, date_to: date, basis: str = "cash") -> dict:
    """
    P&L по месяцам.

    basis: 'cash'|'accrual' — сейчас обе логики используют FinanceOperation.date
    (закладываем интерфейс под будущую модель начислений).
    """
    months = month_starts(date_from, date_to)
    qs = (
        FinanceOperation.objects.filter(company=company, date__gte=date_from, date__lte=date_to)
        .exclude(type=FinanceOperation.TYPE_TRANSFER)
        .select_related("category")
    )

    rows = (
        qs.annotate(month=TruncMonth("date"))
        .values("month", "type", "category__pnl_group")
        .annotate(amount=Sum("amount"))
        .order_by("month")
    )

    # buckets: month -> bucket_key -> Decimal
    buckets: dict[date, dict[str, Decimal]] = {m: {} for m in months}
    for r in rows:
        m = r["month"]
        if not m:
            continue
        m = date(m.year, m.month, 1)
        if m not in buckets:
            continue
        bucket = default_pnl_bucket(r["type"], r["category__pnl_group"])
        if bucket == "ignore":
            continue
        buckets[m][bucket] = buckets[m].get(bucket, Decimal("0")) + (r["amount"] or Decimal("0"))

    def line(key: str, label: str) -> MonthlyReportLine:
        return MonthlyReportLine(
            key=key,
            label=label,
            months=months,
            values={m: buckets[m].get(key, Decimal("0")) for m in months},
        )

    revenue = line(FinanceCategory.PNL_REVENUE, "Выручка")
    var_exp = line(FinanceCategory.PNL_VARIABLE_EXPENSE, "Переменные расходы")
    fixed_exp = line(FinanceCategory.PNL_FIXED_EXPENSE, "Постоянные расходы")
    other_income = line(FinanceCategory.PNL_OTHER_INCOME, "Прочие доходы")
    other_exp = line(FinanceCategory.PNL_OTHER_EXPENSE, "Прочие расходы")
    interest = line(FinanceCategory.PNL_INTEREST, "Проценты")
    taxes = line(FinanceCategory.PNL_TAXES, "Налоги")
    depr = line(FinanceCategory.PNL_DEPRECIATION, "Амортизация")

    def calc_derived(key: str, label: str, fn) -> MonthlyReportLine:
        return MonthlyReportLine(
            key=key,
            label=label,
            months=months,
            values={m: fn(m) for m in months},
        )

    gross_profit = calc_derived(
        "gross_profit",
        "Валовая прибыль",
        lambda m: revenue.values[m] - var_exp.values[m],
    )
    op_profit = calc_derived(
        "operating_profit",
        "Операционная прибыль",
        lambda m: gross_profit.values[m] - fixed_exp.values[m],
    )
    ebitda = calc_derived(
        "ebitda",
        "EBITDA",
        lambda m: op_profit.values[m] + other_income.values[m] - other_exp.values[m],
    )
    net_profit = calc_derived(
        "net_profit",
        "Чистая прибыль",
        lambda m: ebitda.values[m] - interest.values[m] - taxes.values[m] - depr.values[m],
    )

    lines = [
        revenue,
        var_exp,
        gross_profit,
        fixed_exp,
        op_profit,
        other_income,
        other_exp,
        ebitda,
        interest,
        taxes,
        depr,
        net_profit,
    ]

    return {
        "basis": basis,
        "months": months,
        "lines": lines,
    }


def build_cashflow(company, date_from: date, date_to: date, basis: str = "cash") -> dict:
    """
    Cash Flow по месяцам: Операционная / Инвестиционная / Финансовая.
    Используем FinanceOperation (income=+amount, expense=-amount). Переводы исключаем.
    """
    months = month_starts(date_from, date_to)
    qs = (
        FinanceOperation.objects.filter(company=company, date__gte=date_from, date__lte=date_to)
        .exclude(type=FinanceOperation.TYPE_TRANSFER)
        .select_related("category")
    )

    signed_amount = Case(
        When(type=FinanceOperation.TYPE_INCOME, then=F("amount")),
        When(type=FinanceOperation.TYPE_EXPENSE, then=Value(0) - F("amount")),
        default=Value(0),
        output_field=DecimalField(max_digits=14, decimal_places=2),
    )

    rows = (
        qs.annotate(month=TruncMonth("date"))
        .values("month", "category__cashflow_group")
        .annotate(amount=Sum(signed_amount))
        .order_by("month")
    )

    buckets: dict[date, dict[str, Decimal]] = {m: {} for m in months}
    for r in rows:
        m = r["month"]
        if not m:
            continue
        m = date(m.year, m.month, 1)
        if m not in buckets:
            continue
        group = (r["category__cashflow_group"] or "").strip() or FinanceCategory.CF_OPERATING
        buckets[m][group] = buckets[m].get(group, Decimal("0")) + (r["amount"] or Decimal("0"))

    def section(key: str, label: str) -> MonthlyReportLine:
        return MonthlyReportLine(
            key=key,
            label=label,
            months=months,
            values={m: buckets[m].get(key, Decimal("0")) for m in months},
        )

    operating = section(FinanceCategory.CF_OPERATING, "Операционная деятельность")
    investing = section(FinanceCategory.CF_INVESTING, "Инвестиционная деятельность")
    financing = section(FinanceCategory.CF_FINANCING, "Финансовая деятельность")

    net = MonthlyReportLine(
        key="net_cashflow",
        label="Чистый денежный поток",
        months=months,
        values={m: operating.values[m] + investing.values[m] + financing.values[m] for m in months},
    )

    return {
        "basis": basis,
        "months": months,
        "sections": [operating, investing, financing, net],
    }


def build_project_report(company, project: Project, date_from: date, date_to: date) -> dict:
    """
    Проектный отчёт:
    - План: SupplyRequest.total_plan
    - Факт: доход/расход из FinanceOperation + списание со складов проекта (WarehouseOperation.outgoing)
    """
    plan = (
        SupplyRequest.objects.filter(company=company, project=project, required_date__gte=date_from, required_date__lte=date_to)
        .aggregate(total=Sum("total_plan"))
        .get("total")
        or Decimal("0")
    )

    fin = (
        FinanceOperation.objects.filter(company=company, project=project, date__gte=date_from, date__lte=date_to)
        .exclude(type=FinanceOperation.TYPE_TRANSFER)
    )
    income = fin.filter(type=FinanceOperation.TYPE_INCOME).aggregate(total=Sum("amount")).get("total") or Decimal("0")
    expense = fin.filter(type=FinanceOperation.TYPE_EXPENSE).aggregate(total=Sum("amount")).get("total") or Decimal("0")

    # Списание материалов/ресурсов по приобъектным складам проекта
    wh_out = (
        WarehouseOperation.objects.filter(
            company=company,
            operation_type=WarehouseOperation.TYPE_OUTGOING,
            warehouse__project=project,
            created_at__date__gte=date_from,
            created_at__date__lte=date_to,
        )
        .aggregate(total=Sum("total"))
        .get("total")
        or Decimal("0")
    )

    profit = income - expense - wh_out
    margin = (profit / income * Decimal("100")) if income else Decimal("0")

    return {
        "plan_total": plan,
        "fact_income": income,
        "fact_expense": expense,
        "fact_warehouse_outgoing": wh_out,
        "profit": profit,
        "margin_pct": margin,
    }

