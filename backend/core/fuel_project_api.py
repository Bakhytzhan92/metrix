"""
JSON API ГСМ в контексте проекта. Не смешивается с материалами и инвентарём.
"""
from __future__ import annotations

import json
import uuid
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from collections import defaultdict

from django.db.models import Q, Sum
from django.http import HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET, require_http_methods

from .access_utils import has_permission
from .fuel_services import (
    apply_fuel_incoming,
    apply_fuel_issue,
    apply_fuel_writeoff,
    ensure_default_fuel_types,
)
from .inventory_services import get_written_off_warehouse
from .models import Equipment, FuelStock, FuelTransaction, FuelType, Project, Warehouse
from .rbac import permission_required


def _json(body: dict[str, Any], status: int = 200) -> JsonResponse:
    return JsonResponse(body, status=status, json_dumps_params={"ensure_ascii": False})


def _default_gsm_warehouse_for_project(
    project: Project, warehouses: list[Warehouse]
) -> Warehouse | None:
    """
    Склад по умолчанию для операций ГСМ в контексте проекта: среди складов проекта
    выбирается тот, где суммарный остаток топлива (без «газа») больше; иначе первый по имени.
    """
    if not warehouses:
        return None
    wo = get_written_off_warehouse(project.company)
    project_rows = [w for w in warehouses if w.project_id == project.id and w.pk != wo.pk]
    candidates = project_rows if project_rows else [w for w in warehouses if w.pk != wo.pk]
    if not candidates:
        candidates = list(warehouses)

    company = project.company
    best_wh: Warehouse | None = None
    best_sum = Decimal("-1")
    for w in candidates:
        agg = (
            FuelStock.objects.filter(warehouse_id=w.id, fuel_type__company=company)
            .exclude(fuel_type__code="gas")
            .aggregate(s=Sum("quantity"))["s"]
            or Decimal("0")
        )
        if agg > best_sum:
            best_sum = agg
            best_wh = w
    return best_wh or sorted(candidates, key=lambda x: x.name)[0]


def _gsm_warehouse_from_body_or_default(
    body: dict[str, Any],
    project: Project,
    warehouses: list[Warehouse],
    wh_ids: list[int],
) -> Warehouse | None:
    wh_id = body.get("warehouse_id")
    if wh_id not in (None, ""):
        warehouse = get_object_or_404(
            Warehouse, pk=int(wh_id), company=project.company, is_deleted=False
        )
    else:
        warehouse = _default_gsm_warehouse_for_project(project, warehouses)
    if not warehouse or warehouse.id not in wh_ids:
        return None
    return warehouse


def _gsm_warehouse_for_draw(
    body: dict[str, Any],
    fuel_type: FuelType,
    quantity: Decimal,
    project: Project,
    warehouses: list[Warehouse],
    wh_ids: list[int],
) -> Warehouse | None:
    """
    Склад для выдачи/списания: явный warehouse_id в теле запроса или
    первый склад проекта, где остаток >= quantity (сначала основной ГСМ-склад,
    затем остальные по алфавиту).
    """
    wh_id = body.get("warehouse_id")
    if wh_id not in (None, ""):
        warehouse = get_object_or_404(
            Warehouse, pk=int(wh_id), company=project.company, is_deleted=False
        )
        if warehouse.id not in wh_ids:
            return None
        return warehouse

    preferred = _default_gsm_warehouse_for_project(project, warehouses)
    in_scope = [w for w in warehouses if w.id in wh_ids]
    ordered: list[Warehouse] = []
    seen: set[int] = set()
    if preferred and preferred.id in wh_ids:
        ordered.append(preferred)
        seen.add(preferred.id)
    for w in sorted(in_scope, key=lambda x: x.name):
        if w.id in seen:
            continue
        ordered.append(w)

    for w in ordered:
        try:
            st = FuelStock.objects.get(warehouse=w, fuel_type=fuel_type)
        except FuelStock.DoesNotExist:
            continue
        if (st.quantity or Decimal("0")) >= quantity:
            return w
    return None


def _fuel_dashboard_cards(
    company, wh_ids: list[int]
) -> tuple[list[dict[str, Any]], list[str]]:
    """Карточки основных видов топлива: остаток по складам проекта, расход за месяц, даты."""
    from django.db.models import Sum

    CARD_CODES = ("ai92", "ai95", "diesel")
    ensure_default_fuel_types(company)
    alerts: list[str] = []
    cards: list[dict[str, Any]] = []
    month_start = date.today().replace(day=1)
    for ft in FuelType.objects.filter(company=company, code__in=CARD_CODES).order_by(
        "code"
    ):
        stocks = list(
            FuelStock.objects.filter(warehouse_id__in=wh_ids, fuel_type=ft).select_related(
                "warehouse"
            )
        )
        balance = sum((s.quantity or Decimal("0") for s in stocks), Decimal("0"))
        tq = sum((s.quantity or Decimal("0") for s in stocks), Decimal("0"))
        if tq > 0:
            avg_price = (
                sum(
                    (s.quantity or Decimal("0")) * (s.price_avg or Decimal("0"))
                    for s in stocks
                )
                / tq
            )
        else:
            avg_price = Decimal("0")
        tx_m = FuelTransaction.objects.filter(
            warehouse_id__in=wh_ids,
            fuel_type=ft,
            date__gte=month_start,
            movement_type__in=[
                FuelTransaction.TYPE_ISSUE,
                FuelTransaction.TYPE_WRITEOFF,
            ],
        ).aggregate(s=Sum("quantity"))
        month_out = tx_m["s"] or Decimal("0")
        last_issue = (
            FuelTransaction.objects.filter(
                warehouse_id__in=wh_ids,
                fuel_type=ft,
                movement_type=FuelTransaction.TYPE_ISSUE,
            )
            .order_by("-date", "-created_at")
            .first()
        )
        last_wo = (
            FuelTransaction.objects.filter(
                warehouse_id__in=wh_ids,
                fuel_type=ft,
                movement_type=FuelTransaction.TYPE_WRITEOFF,
            )
            .order_by("-date", "-created_at")
            .first()
        )
        low = ft.unit == "л" and balance < Decimal("500")
        if low:
            alerts.append(f"Низкий остаток «{ft.name}»: {_fmt_qty(balance)} {ft.unit}")
        cards.append(
            {
                "fuel_type_id": ft.id,
                "code": ft.code,
                "name": ft.name,
                "unit": ft.unit,
                "balance": _fmt_qty(balance),
                "avg_price": _fmt_money(avg_price),
                "month_out": _fmt_qty(month_out),
                "last_issue_date": last_issue.date.isoformat() if last_issue else "",
                "last_writeoff_date": last_wo.date.isoformat() if last_wo else "",
                "low_balance": low,
            }
        )
    return cards, alerts


def _parse_date(s: str | None):
    if not s:
        return None
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _parse_decimal(s: Any) -> Decimal | None:
    if s is None or s == "":
        return None
    try:
        return Decimal(str(s).replace(",", "."))
    except (InvalidOperation, ValueError):
        return None


def _strip_trailing_zeros(s: str) -> str:
    if "." not in s:
        return s
    s = s.rstrip("0").rstrip(".")
    return s if s else "0"


def _fmt_money(d: Decimal) -> str:
    from decimal import ROUND_HALF_UP

    q = (d or Decimal("0")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return _strip_trailing_zeros(format(q, "f"))


def _fmt_qty(d: Decimal) -> str:
    from decimal import ROUND_HALF_UP

    q = (d or Decimal("0")).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    return _strip_trailing_zeros(format(q, "f"))


def _can_edit(user, company) -> bool:
    return has_permission(user, company, "edit_warehouse")


def _project_and_warehouses(request: HttpRequest, pk: int):
    from .views import _get_project_or_403

    project, err = _get_project_or_403(request, pk)
    if err:
        return err, None
    wo = get_written_off_warehouse(project.company)
    warehouses = list(
        Warehouse.objects.filter(company=project.company, is_deleted=False)
        .filter(Q(project=project) | Q(pk=wo.pk))
        .order_by("name")
    )
    wh_ids = [w.id for w in warehouses]
    return None, (project, warehouses, wh_ids)


@require_GET
@permission_required("view_warehouse")
def api_project_gsm_meta(request: HttpRequest, pk: int) -> JsonResponse:
    err, data = _project_and_warehouses(request, pk)
    if err:
        return err
    project, warehouses, _ = data
    company = project.company
    ensure_default_fuel_types(company)
    wh_ids_list = [w.id for w in warehouses]
    gw = _default_gsm_warehouse_for_project(project, warehouses)
    types = list(
        FuelType.objects.filter(company=company)
        .exclude(code="gas")
        .order_by("code")
        .values("id", "code", "name", "unit")
    )
    equipment = list(
        Equipment.objects.filter(company=company)
        .select_related("fuel_type", "project")
        .order_by("name")[:1000]
    )
    eq_json = [
        {
            "id": e.id,
            "name": e.name,
            "display": (
                f"{e.name} ({e.license_plate})" if e.license_plate else e.name
            ),
            "fuel_type_id": e.fuel_type_id,
            "status": e.status,
            "project_id": e.project_id,
            "consumption_norm_liters": _fmt_qty(e.consumption_norm_liters or Decimal("0"))
            if e.consumption_norm_liters
            else "",
            "consumption_norm_mode": e.consumption_norm_mode,
            "tank_l": _fmt_qty(e.tank_capacity_liters or Decimal("0"))
            if e.tank_capacity_liters
            else "",
            "engine_hours": _fmt_qty(e.engine_hours or Decimal("0"))
            if e.engine_hours
            else "",
        }
        for e in equipment
    ]
    fuel_cards, fuel_alerts = _fuel_dashboard_cards(company, wh_ids_list)
    return _json(
        {
            "ok": True,
            "can_edit": _can_edit(request.user, company),
            "warehouses": [{"id": w.id, "name": w.name} for w in warehouses],
            "gsm_warehouse": (
                {"id": gw.id, "name": gw.name} if gw else None
            ),
            "fuel_types": types,
            "equipment": eq_json,
            "fuel_cards": fuel_cards,
            "fuel_alerts": fuel_alerts,
            "recipient_types": [
                {"value": k, "label": str(v)}
                for k, v in FuelTransaction.RECIPIENT_CHOICES
            ],
            "writeoff_reasons": [
                {"value": k, "label": str(v)}
                for k, v in FuelTransaction.WRITEOFF_REASON_CHOICES
            ],
            "movement_types": [
                {"value": k, "label": str(v)} for k, v in FuelTransaction.TYPE_CHOICES
            ],
        }
    )


@require_GET
@permission_required("view_warehouse")
def api_project_gsm_stocks(request: HttpRequest, pk: int) -> JsonResponse:
    err, data = _project_and_warehouses(request, pk)
    if err:
        return err
    project, _, wh_ids = data
    company = project.company
    ensure_default_fuel_types(company)
    q_raw = (request.GET.get("q") or "").strip()
    q = q_raw.lower()
    ft_f = request.GET.get("fuel_type")
    sort = (request.GET.get("sort") or "fuel").strip()
    order = (request.GET.get("order") or "asc").strip()

    qs = FuelStock.objects.filter(
        warehouse_id__in=wh_ids, fuel_type__company=company
    ).exclude(fuel_type__code="gas").select_related("fuel_type")
    if q_raw:
        qs = qs.filter(
            Q(fuel_type__name__icontains=q_raw) | Q(fuel_type__code__icontains=q_raw)
        )
    if ft_f and str(ft_f).isdigit():
        qs = qs.filter(fuel_type_id=int(ft_f))

    buckets: defaultdict[int, list[FuelStock]] = defaultdict(list)
    for s in qs:
        buckets[s.fuel_type_id].append(s)

    rows: list[dict[str, Any]] = []
    for _ft_id, items in buckets.items():
        ft = items[0].fuel_type
        qty = sum((s.quantity or Decimal("0") for s in items), Decimal("0"))
        if qty > 0:
            price_avg = (
                sum(
                    (s.quantity or Decimal("0")) * (s.price_avg or Decimal("0"))
                    for s in items
                )
                / qty
            )
        else:
            price_avg = Decimal("0")
        total = qty * price_avg
        rep = min(items, key=lambda x: x.id)
        rows.append(
            {
                "stock_id": rep.id,
                "fuel_type_id": ft.id,
                "fuel_name": ft.name,
                "unit": ft.unit,
                "quantity": _fmt_qty(qty),
                "price": _fmt_money(price_avg),
                "total_value": _fmt_money(total),
            }
        )

    rev = order == "desc"
    if sort == "quantity":
        rows.sort(key=lambda r: Decimal(r["quantity"]), reverse=rev)
    elif sort == "price":
        rows.sort(key=lambda r: Decimal(r["price"]), reverse=rev)
    elif sort == "total":
        rows.sort(key=lambda r: Decimal(r["total_value"]), reverse=rev)
    else:
        rows.sort(key=lambda r: (r["fuel_name"] or "").lower(), reverse=rev)

    return _json({"ok": True, "stocks": rows})


@require_GET
@permission_required("view_warehouse")
def api_project_gsm_history(request: HttpRequest, pk: int) -> JsonResponse:
    err, data = _project_and_warehouses(request, pk)
    if err:
        return err
    project, _, wh_ids = data
    company = project.company
    mt = (request.GET.get("movement_type") or "").strip()
    df = _parse_date(request.GET.get("date_from"))
    dt = _parse_date(request.GET.get("date_to"))
    eq_f = request.GET.get("equipment_id")
    ft_hf = request.GET.get("fuel_type_id")
    proj_hf = request.GET.get("project_id")
    qs = FuelTransaction.objects.filter(
        warehouse_id__in=wh_ids, fuel_type__company=company
    ).exclude(fuel_type__code="gas").select_related("fuel_type", "warehouse", "user", "target_project", "equipment")
    if mt and mt in dict(FuelTransaction.TYPE_CHOICES):
        qs = qs.filter(movement_type=mt)
    if df:
        qs = qs.filter(date__gte=df)
    if dt:
        qs = qs.filter(date__lte=dt)
    if eq_f and str(eq_f).isdigit():
        qs = qs.filter(equipment_id=int(eq_f))
    if ft_hf and str(ft_hf).isdigit():
        qs = qs.filter(fuel_type_id=int(ft_hf))
    if proj_hf and str(proj_hf).isdigit():
        qs = qs.filter(target_project_id=int(proj_hf))
    qs = qs.order_by("-date", "-created_at")[:2000]
    entries = []
    for m in qs:
        op = dict(FuelTransaction.TYPE_CHOICES).get(m.movement_type, m.movement_type)
        entries.append(
            {
                "id": m.id,
                "date": m.date.isoformat(),
                "operation_display": op,
                "movement_type": m.movement_type,
                "fuel_name": m.fuel_type.name,
                "unit": m.fuel_type.unit,
                "quantity": _fmt_qty(m.quantity or Decimal("0")),
                "total": _fmt_money(m.total or Decimal("0")),
                "username": m.user.get_username() if m.user else None,
                "driver_name": m.driver_name,
                "equipment_label": (
                    m.equipment.name
                    if m.equipment_id
                    else (m.equipment_name or "")
                ),
                "comment": m.comment,
                "supplier": m.supplier,
                "document_number": m.document_number,
                "recipient_display": dict(FuelTransaction.RECIPIENT_CHOICES).get(
                    m.recipient_type, ""
                ),
                "issued_to_name": m.issued_to_name,
                "equipment_name": m.equipment_name,
                "contractor_name": m.contractor_name,
                "target_project_name": m.target_project.name if m.target_project_id else "",
                "writeoff_reason_display": dict(
                    FuelTransaction.WRITEOFF_REASON_CHOICES
                ).get(m.writeoff_reason, ""),
            }
        )
    return _json({"ok": True, "entries": entries})


@require_GET
@permission_required("view_warehouse")
def api_project_gsm_analytics(request: HttpRequest, pk: int) -> JsonResponse:
    err, data = _project_and_warehouses(request, pk)
    if err:
        return err
    project, _, wh_ids = data
    company = project.company
    group = (request.GET.get("group_by") or "project").strip()
    df = _parse_date(request.GET.get("date_from"))
    dt = _parse_date(request.GET.get("date_to"))
    qs = FuelTransaction.objects.filter(
        warehouse_id__in=wh_ids,
        fuel_type__company=company,
        movement_type__in=[FuelTransaction.TYPE_ISSUE, FuelTransaction.TYPE_WRITEOFF],
    ).exclude(fuel_type__code="gas")
    if df:
        qs = qs.filter(date__gte=df)
    if dt:
        qs = qs.filter(date__lte=dt)

    if group == "equipment":
        rows = (
            qs.values("equipment_name")
            .annotate(total_qty=Sum("quantity"))
            .order_by("-total_qty")[:200]
        )
        out = [
            {
                "key": r["equipment_name"] or "—",
                "label": r["equipment_name"] or "—",
                "quantity": _fmt_qty(r["total_qty"] or Decimal("0")),
            }
            for r in rows
        ]
    elif group == "employee":
        rows = (
            qs.filter(recipient_type=FuelTransaction.RECIPIENT_EMPLOYEE)
            .values("issued_to_name")
            .annotate(total_qty=Sum("quantity"))
            .order_by("-total_qty")[:200]
        )
        out = [
            {
                "key": r["issued_to_name"] or "—",
                "label": r["issued_to_name"] or "—",
                "quantity": _fmt_qty(r["total_qty"] or Decimal("0")),
            }
            for r in rows
        ]
    elif group == "contractor":
        rows = (
            qs.filter(recipient_type=FuelTransaction.RECIPIENT_CONTRACTOR)
            .values("contractor_name")
            .annotate(total_qty=Sum("quantity"))
            .order_by("-total_qty")[:200]
        )
        out = [
            {
                "key": r["contractor_name"] or "—",
                "label": r["contractor_name"] or "—",
                "quantity": _fmt_qty(r["total_qty"] or Decimal("0")),
            }
            for r in rows
        ]
    else:
        rows = (
            qs.values("target_project_id", "target_project__name")
            .annotate(total_qty=Sum("quantity"))
            .order_by("-total_qty")[:200]
        )
        out = [
            {
                "key": str(r["target_project_id"] or ""),
                "label": r["target_project__name"] or "—",
                "quantity": _fmt_qty(r["total_qty"] or Decimal("0")),
            }
            for r in rows
        ]
    return _json({"ok": True, "group_by": group, "rows": out})


@require_http_methods(["POST"])
@permission_required("view_warehouse")
def api_project_gsm_incoming(request: HttpRequest, pk: int) -> JsonResponse:
    err, data = _project_and_warehouses(request, pk)
    if err:
        return err
    project, warehouses, wh_ids = data
    company = project.company
    if not _can_edit(request.user, company):
        return _json({"ok": False, "error": "forbidden"}, status=403)
    body = json.loads(request.body or b"{}")
    ft_id = body.get("fuel_type_id")
    fuel_type = get_object_or_404(FuelType, pk=int(ft_id), company=company)
    if fuel_type.code == "gas":
        return _json(
            {"ok": False, "error": "Вид топлива «Газ» не используется"},
            status=400,
        )
    warehouse = _gsm_warehouse_from_body_or_default(body, project, warehouses, wh_ids)
    if warehouse is None:
        return _json({"ok": False, "error": "invalid_warehouse"}, status=400)
    qty = _parse_decimal(body.get("quantity"))
    price = _parse_decimal(body.get("price")) or Decimal("0")
    if not qty or qty <= 0:
        return _json({"ok": False, "error": "bad_quantity"}, status=400)
    try:
        apply_fuel_incoming(
            fuel_type=fuel_type,
            warehouse=warehouse,
            quantity=qty,
            price=price,
            date=_parse_date(body.get("date")) or date.today(),
            comment=(body.get("comment") or "")[:500],
            supplier=(body.get("supplier") or "")[:255],
            document_number=(body.get("document_number") or "")[:120],
            user=request.user,
        )
    except ValueError as e:
        return _json({"ok": False, "error": str(e)[:500]}, status=400)
    return _json({"ok": True})


@require_http_methods(["POST"])
@permission_required("view_warehouse")
def api_project_gsm_issue(request: HttpRequest, pk: int) -> JsonResponse:
    err, data = _project_and_warehouses(request, pk)
    if err:
        return err
    project, warehouses, wh_ids = data
    company = project.company
    if not _can_edit(request.user, company):
        return _json({"ok": False, "error": "forbidden"}, status=403)
    body = json.loads(request.body or b"{}")
    ft_id = body.get("fuel_type_id")
    fuel_type = get_object_or_404(FuelType, pk=int(ft_id), company=company)
    if fuel_type.code == "gas":
        return _json(
            {"ok": False, "error": "Вид топлива «Газ» не используется"},
            status=400,
        )
    qty = _parse_decimal(body.get("quantity"))
    if not qty or qty <= 0:
        return _json({"ok": False, "error": "bad_quantity"}, status=400)
    warehouse = _gsm_warehouse_for_draw(
        body, fuel_type, qty, project, warehouses, wh_ids
    )
    if warehouse is None:
        return _json(
            {
                "ok": False,
                "error": "Недостаточно топлива на складах проекта или нет строки остатка",
            },
            status=400,
        )
    rtype = (body.get("recipient_type") or "")[:20]
    if rtype not in dict(FuelTransaction.RECIPIENT_CHOICES):
        return _json({"ok": False, "error": "bad_recipient_type"}, status=400)
    eq = None
    eq_id = body.get("equipment_id")
    if eq_id and str(eq_id).isdigit():
        eq = get_object_or_404(Equipment, pk=int(eq_id), company=company)
    tp = None
    tp_id = body.get("target_project_id")
    if tp_id and str(tp_id).isdigit():
        tp = get_object_or_404(Project, pk=int(tp_id), company=company)
    price_override = _parse_decimal(body.get("price"))
    driver_name = (body.get("driver_name") or "")[:255]
    norm_warning = ""
    work_hours = _parse_decimal(body.get("work_hours"))
    try:
        apply_fuel_issue(
            fuel_type=fuel_type,
            warehouse=warehouse,
            quantity=qty,
            date=_parse_date(body.get("date")) or date.today(),
            price=price_override,
            comment=(body.get("comment") or "")[:500],
            recipient_type=rtype,
            issued_to_name=(body.get("issued_to_name") or "")[:255],
            driver_name=driver_name,
            equipment_name=(body.get("equipment_name") or "")[:255],
            equipment=eq,
            target_project=tp,
            contractor_name=(body.get("contractor_name") or "")[:255],
            user=request.user,
        )
    except FuelStock.DoesNotExist:
        return _json({"ok": False, "error": "no_stock_row"}, status=400)
    except ValueError as e:
        return _json({"ok": False, "error": str(e)[:500]}, status=400)
    if (
        eq
        and work_hours
        and work_hours > 0
        and eq.consumption_norm_liters
        and eq.consumption_norm_liters > 0
    ):
        if eq.consumption_norm_mode == Equipment.NORM_PER_HOUR:
            expected = eq.consumption_norm_liters * work_hours
        else:
            expected = Decimal("0")
        if expected > 0 and qty > expected * Decimal("1.05"):
            pct = int((qty / expected - Decimal("1")) * Decimal("100"))
            norm_warning = (
                f"«{eq.name}»: расход выше нормы примерно на {pct}% "
                f"(ожид. ~{_fmt_qty(expected)} {fuel_type.unit} за {_fmt_qty(work_hours)} ч)."
            )
    out: dict[str, Any] = {"ok": True}
    if norm_warning:
        out["norm_warning"] = norm_warning
    return _json(out)


@require_http_methods(["POST"])
@permission_required("view_warehouse")
def api_project_gsm_writeoff(request: HttpRequest, pk: int) -> JsonResponse:
    err, data = _project_and_warehouses(request, pk)
    if err:
        return err
    project, warehouses, wh_ids = data
    company = project.company
    if not _can_edit(request.user, company):
        return _json({"ok": False, "error": "forbidden"}, status=403)
    body = json.loads(request.body or b"{}")
    ft_id = body.get("fuel_type_id")
    fuel_type = get_object_or_404(FuelType, pk=int(ft_id), company=company)
    if fuel_type.code == "gas":
        return _json(
            {"ok": False, "error": "Вид топлива «Газ» не используется"},
            status=400,
        )
    qty = _parse_decimal(body.get("quantity"))
    if not qty or qty <= 0:
        return _json({"ok": False, "error": "bad_quantity"}, status=400)
    warehouse = _gsm_warehouse_for_draw(
        body, fuel_type, qty, project, warehouses, wh_ids
    )
    if warehouse is None:
        return _json(
            {
                "ok": False,
                "error": "Недостаточно топлива на складах проекта или нет строки остатка",
            },
            status=400,
        )
    reason = (body.get("writeoff_reason") or "")[:20]
    try:
        apply_fuel_writeoff(
            fuel_type=fuel_type,
            warehouse=warehouse,
            quantity=qty,
            date=_parse_date(body.get("date")) or date.today(),
            writeoff_reason=reason,
            comment=(body.get("comment") or "")[:500],
            user=request.user,
        )
    except FuelStock.DoesNotExist:
        return _json({"ok": False, "error": "no_stock_row"}, status=400)
    except ValueError as e:
        return _json({"ok": False, "error": str(e)[:500]}, status=400)
    return _json({"ok": True})


@require_http_methods(["POST"])
@permission_required("view_warehouse")
def api_project_gsm_fuel_type_create(request: HttpRequest, pk: int) -> JsonResponse:
    err, data = _project_and_warehouses(request, pk)
    if err:
        return err
    project, _, _ = data
    company = project.company
    if not _can_edit(request.user, company):
        return _json({"ok": False, "error": "forbidden"}, status=403)
    body = json.loads(request.body or b"{}")
    name = (body.get("name") or "").strip()
    unit = (body.get("unit") or "л").strip()[:30] or "л"
    if not name:
        return _json({"ok": False, "error": "name_required"}, status=400)
    code = f"other_{uuid.uuid4().hex[:10]}"
    ft = FuelType.objects.create(company=company, code=code, name=name, unit=unit)
    return _json(
        {
            "ok": True,
            "fuel_type": {"id": ft.id, "code": ft.code, "name": ft.name, "unit": ft.unit},
        }
    )


@require_GET
@permission_required("view_warehouse")
def api_project_gsm_timeseries(request: HttpRequest, pk: int) -> JsonResponse:
    err, data = _project_and_warehouses(request, pk)
    if err:
        return err
    project, _, wh_ids = data
    company = project.company
    gran = (request.GET.get("granularity") or "day").strip()
    df = _parse_date(request.GET.get("date_from"))
    dt = _parse_date(request.GET.get("date_to"))
    qs = FuelTransaction.objects.filter(
        warehouse_id__in=wh_ids,
        fuel_type__company=company,
        movement_type__in=[
            FuelTransaction.TYPE_ISSUE,
            FuelTransaction.TYPE_WRITEOFF,
        ],
    ).exclude(fuel_type__code="gas")
    if df:
        qs = qs.filter(date__gte=df)
    if dt:
        qs = qs.filter(date__lte=dt)
    from django.db.models.functions import TruncDay, TruncMonth

    if gran == "month":
        rows = (
            qs.annotate(p=TruncMonth("date"))
            .values("p")
            .annotate(total_qty=Sum("quantity"))
            .order_by("p")
        )
    else:
        rows = (
            qs.annotate(p=TruncDay("date"))
            .values("p")
            .annotate(total_qty=Sum("quantity"))
            .order_by("p")
        )
    points = []
    for r in rows:
        p = r["p"]
        if p is None:
            key = ""
        elif hasattr(p, "date"):
            key = p.date().isoformat()
        else:
            key = str(p)[:10]
        points.append(
            {
                "key": key,
                "quantity": _fmt_qty(r["total_qty"] or Decimal("0")),
            }
        )
    return _json({"ok": True, "granularity": gran, "points": points})
