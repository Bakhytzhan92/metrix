"""
JSON API материалов в контексте проекта (остатки, операции, история).
Не смешивается с инвентарём (WarehouseInventoryItem).
"""
from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from django.db import transaction
from django.db.models import Q
from django.http import HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET, require_http_methods

from .access_utils import has_permission
from .inventory_services import get_written_off_warehouse
from .models import Material, ProjectSchedulePhase, Stock, StockMovement, Warehouse
from .rbac import permission_required
from .warehouse_services import (
    apply_incoming,
    apply_outgoing_consumption,
    apply_transfer,
    apply_writeoff,
)


def _json(body: dict[str, Any], status: int = 200) -> JsonResponse:
    return JsonResponse(body, status=status, json_dumps_params={"ensure_ascii": False})


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
    """Деньги: до 2 знаков, без лишних нулей."""
    from decimal import ROUND_HALF_UP

    q = (d or Decimal("0")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return _strip_trailing_zeros(format(q, "f"))


def _fmt_qty(d: Decimal) -> str:
    """Количество: до 4 знаков, без лишних нулей."""
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


def _stock_status(row_qty: Decimal) -> str:
    if row_qty and row_qty > 0:
        return "in_stock"
    return "empty"


def _stock_status_label(code: str) -> str:
    return "В наличии" if code == "in_stock" else "Нет остатка"


@require_GET
@permission_required("view_warehouse")
def api_project_materials_meta(request: HttpRequest, pk: int) -> JsonResponse:
    err, data = _project_and_warehouses(request, pk)
    if err:
        return err
    project, warehouses, wh_ids = data
    company = project.company
    phases = list(
        ProjectSchedulePhase.objects.filter(project=project)
        .order_by("order", "id")[:500]
        .values("id", "name", "estimate_section_id")
    )
    for p in phases:
        p["label"] = p.get("name") or f"Этап #{p['id']}"
    return _json(
        {
            "ok": True,
            "project_id": project.pk,
            "can_edit": _can_edit(request.user, company),
            "warehouses": [{"id": w.id, "name": w.name} for w in warehouses],
            "writeoff_reasons": [{"value": k, "label": str(v)} for k, v in StockMovement.WRITEOFF_REASON_CHOICES],
            "movement_types": [{"value": k, "label": str(v)} for k, v in StockMovement.TYPE_CHOICES],
            "schedule_phases": phases,
        }
    )


@require_GET
@permission_required("view_warehouse")
def api_project_materials_catalog(request: HttpRequest, pk: int) -> JsonResponse:
    err, data = _project_and_warehouses(request, pk)
    if err:
        return err
    project, _, _ = data
    company = project.company
    materials = list(
        Material.objects.filter(company=company)
        .order_by("name")
        .values("id", "name", "unit")
    )
    return _json({"ok": True, "materials": materials})


@require_GET
@permission_required("view_warehouse")
def api_project_materials_stocks(request: HttpRequest, pk: int) -> JsonResponse:
    err, data = _project_and_warehouses(request, pk)
    if err:
        return err
    project, warehouses, wh_ids = data
    company = project.company
    q = (request.GET.get("q") or "").strip()
    wh_f = request.GET.get("warehouse")
    sort = request.GET.get("sort") or "name"
    order = request.GET.get("order") or "asc"

    qs = (
        Stock.objects.filter(warehouse_id__in=wh_ids, material__company=company)
        .select_related("material", "warehouse")
    )
    if q:
        qs = qs.filter(material__name__icontains=q)
    if wh_f and str(wh_f).isdigit():
        qs = qs.filter(warehouse_id=int(wh_f))

    sort_map = {
        "name": "material__name",
        "quantity": "quantity",
        "price": "price_avg",
        "total": "line_total",
        "warehouse": "warehouse__name",
    }
    col = sort_map.get(sort, "material__name")
    from django.db.models import DecimalField, ExpressionWrapper, F

    qs = qs.annotate(
        line_total=ExpressionWrapper(
            F("quantity") * F("price_avg"),
            output_field=DecimalField(max_digits=24, decimal_places=8),
        )
    )
    if sort == "total":
        qs = qs.order_by(f"{'-' if order == 'desc' else ''}line_total")
    elif order == "desc":
        qs = qs.order_by(f"-{col}")
    else:
        qs = qs.order_by(col)

    rows = []
    for s in qs:
        qty = s.quantity or Decimal("0")
        price = s.price_avg or Decimal("0")
        total = qty * price
        st = _stock_status(qty)
        rows.append(
            {
                "stock_id": s.id,
                "material_id": s.material_id,
                "name": s.material.name,
                "unit": s.material.unit,
                "quantity": _fmt_qty(qty),
                "price": _fmt_money(price),
                "total_value": _fmt_money(total),
                "warehouse_id": s.warehouse_id,
                "warehouse_name": s.warehouse.name,
                "status": st,
                "status_display": _stock_status_label(st),
                "supplier": s.material.supplier or "",
                "description": (s.material.description or "")[:200],
            }
        )
    return _json({"ok": True, "stocks": rows})


@require_GET
@permission_required("view_warehouse")
def api_project_materials_history(request: HttpRequest, pk: int) -> JsonResponse:
    err, data = _project_and_warehouses(request, pk)
    if err:
        return err
    project, warehouses, wh_ids = data
    company = project.company
    mt = (request.GET.get("movement_type") or "").strip()
    qs = (
        StockMovement.objects.filter(material__company=company)
        .filter(
            Q(warehouse_from_id__in=wh_ids)
            | Q(warehouse_to_id__in=wh_ids)
            | Q(project_id=project.pk)
        )
        .select_related("material", "warehouse_from", "warehouse_to", "project", "user", "schedule_phase")
        .order_by("-date", "-created_at")[:500]
    )
    if mt and mt in dict(StockMovement.TYPE_CHOICES):
        qs = qs.filter(movement_type=mt)

    entries = []
    for m in qs:
        entries.append(
            {
                "id": m.id,
                "date": str(m.date),
                "movement_type": m.movement_type,
                "movement_type_display": m.get_movement_type_display(),
                "material_id": m.material_id,
                "material_name": m.material.name,
                "quantity": _fmt_qty(m.quantity or Decimal("0")),
                "unit": m.material.unit,
                "price": _fmt_money(m.price or Decimal("0")),
                "total": _fmt_money(m.total or Decimal("0")),
                "warehouse_from": m.warehouse_from.name if m.warehouse_from else None,
                "warehouse_to": m.warehouse_to.name if m.warehouse_to else None,
                "comment": m.comment,
                "supplier": m.supplier,
                "writeoff_reason": m.writeoff_reason,
                "writeoff_reason_display": dict(StockMovement.WRITEOFF_REASON_CHOICES).get(m.writeoff_reason, ""),
                "username": m.user.get_username() if m.user else None,
                "schedule_phase_label": (
                    m.schedule_phase.name if m.schedule_phase_id else None
                ),
            }
        )
    return _json({"ok": True, "entries": entries})


@require_http_methods(["POST"])
@permission_required("view_warehouse")
def api_project_materials_create(request: HttpRequest, pk: int) -> JsonResponse:
    err, data = _project_and_warehouses(request, pk)
    if err:
        return err
    project, warehouses, wh_ids = data
    company = project.company
    if not _can_edit(request.user, company):
        return _json({"ok": False, "error": "forbidden"}, status=403)

    data = json.loads(request.body or b"{}")
    name = (data.get("name") or "").strip()
    if not name:
        return _json({"ok": False, "error": "name_required"}, status=400)
    unit = (data.get("unit") or "шт").strip()[:30] or "шт"
    wh_id = data.get("warehouse_id")
    warehouse = get_object_or_404(Warehouse, pk=int(wh_id), company=company, is_deleted=False)
    if warehouse.id not in wh_ids:
        return _json({"ok": False, "error": "invalid_warehouse"}, status=400)

    price = _parse_decimal(data.get("unit_price") or data.get("price")) or Decimal("0")
    initial = _parse_decimal(data.get("initial_quantity") or data.get("quantity")) or Decimal("0")
    supplier = (data.get("supplier") or "").strip()[:255]
    description = (data.get("description") or "").strip()

    if Material.objects.filter(company=company, name=name).exists():
        return _json({"ok": False, "error": "material_name_exists"}, status=400)

    try:
        with transaction.atomic():
            mat = Material.objects.create(
                company=company,
                name=name,
                category=Material.CATEGORY_MATERIAL,
                unit=unit,
                supplier=supplier,
                description=description,
            )
            if initial > 0:
                apply_incoming(
                    material=mat,
                    warehouse=warehouse,
                    quantity=initial,
                    price=price,
                    date=_parse_date(data.get("date")) or date.today(),
                    comment="Начальный остаток",
                    supplier=supplier,
                    user=request.user,
                )
            else:
                Stock.objects.get_or_create(
                    warehouse=warehouse,
                    material=mat,
                    defaults={"quantity": Decimal("0"), "price_avg": price},
                )
    except Exception as e:
        return _json({"ok": False, "error": str(e)[:500]}, status=400)

    return _json({"ok": True, "material_id": mat.id})


def _movement_date(data):
    return _parse_date(data.get("date")) or date.today()


@require_http_methods(["POST"])
@permission_required("view_warehouse")
def api_project_materials_incoming(request: HttpRequest, pk: int) -> JsonResponse:
    err, data = _project_and_warehouses(request, pk)
    if err:
        return err
    project, warehouses, wh_ids = data
    company = project.company
    if not _can_edit(request.user, company):
        return _json({"ok": False, "error": "forbidden"}, status=403)
    data = json.loads(request.body or b"{}")
    material = get_object_or_404(Material, pk=int(data.get("material_id")), company=company)
    warehouse = get_object_or_404(Warehouse, pk=int(data.get("warehouse_id")), company=company, is_deleted=False)
    if warehouse.id not in wh_ids:
        return _json({"ok": False, "error": "invalid_warehouse"}, status=400)
    qty = _parse_decimal(data.get("quantity"))
    if not qty or qty <= 0:
        return _json({"ok": False, "error": "bad_quantity"}, status=400)
    price = _parse_decimal(data.get("price")) or Decimal("0")
    try:
        apply_incoming(
            material=material,
            warehouse=warehouse,
            quantity=qty,
            price=price,
            date=_movement_date(data),
            comment=(data.get("comment") or "").strip()[:500],
            supplier=(data.get("supplier") or "").strip()[:255],
            user=request.user,
        )
    except Exception as e:
        return _json({"ok": False, "error": str(e)[:500]}, status=400)
    return _json({"ok": True})


@require_http_methods(["POST"])
@permission_required("view_warehouse")
def api_project_materials_outgoing(request: HttpRequest, pk: int) -> JsonResponse:
    err, data = _project_and_warehouses(request, pk)
    if err:
        return err
    project, warehouses, wh_ids = data
    company = project.company
    if not _can_edit(request.user, company):
        return _json({"ok": False, "error": "forbidden"}, status=403)
    data = json.loads(request.body or b"{}")
    material = get_object_or_404(Material, pk=int(data.get("material_id")), company=company)
    warehouse = get_object_or_404(Warehouse, pk=int(data.get("warehouse_id")), company=company, is_deleted=False)
    if warehouse.id not in wh_ids:
        return _json({"ok": False, "error": "invalid_warehouse"}, status=400)
    qty = _parse_decimal(data.get("quantity"))
    if not qty or qty <= 0:
        return _json({"ok": False, "error": "bad_quantity"}, status=400)
    phase = None
    if data.get("schedule_phase_id") and str(data.get("schedule_phase_id")).isdigit():
        phase = get_object_or_404(
            ProjectSchedulePhase,
            pk=int(data["schedule_phase_id"]),
            project=project,
        )
    try:
        apply_outgoing_consumption(
            material=material,
            warehouse=warehouse,
            quantity=qty,
            date=_movement_date(data),
            project=project,
            schedule_phase=phase,
            comment=(data.get("comment") or "").strip()[:500],
            user=request.user,
        )
    except Stock.DoesNotExist:
        return _json({"ok": False, "error": "no_stock_row"}, status=400)
    except Exception as e:
        return _json({"ok": False, "error": str(e)[:500]}, status=400)
    return _json({"ok": True})


@require_http_methods(["POST"])
@permission_required("view_warehouse")
def api_project_materials_transfer(request: HttpRequest, pk: int) -> JsonResponse:
    err, data = _project_and_warehouses(request, pk)
    if err:
        return err
    project, warehouses, wh_ids = data
    company = project.company
    if not _can_edit(request.user, company):
        return _json({"ok": False, "error": "forbidden"}, status=403)
    data = json.loads(request.body or b"{}")
    material = get_object_or_404(Material, pk=int(data.get("material_id")), company=company)
    wf = get_object_or_404(Warehouse, pk=int(data.get("warehouse_from_id")), company=company, is_deleted=False)
    wt = get_object_or_404(Warehouse, pk=int(data.get("warehouse_to_id")), company=company, is_deleted=False)
    if wf.id not in wh_ids or wt.id not in wh_ids:
        return _json({"ok": False, "error": "invalid_warehouse"}, status=400)
    qty = _parse_decimal(data.get("quantity"))
    if not qty or qty <= 0:
        return _json({"ok": False, "error": "bad_quantity"}, status=400)
    try:
        apply_transfer(
            material=material,
            warehouse_from=wf,
            warehouse_to=wt,
            quantity=qty,
            date=_movement_date(data),
            comment=(data.get("comment") or "").strip()[:500],
            user=request.user,
        )
    except Stock.DoesNotExist:
        return _json({"ok": False, "error": "no_stock_row"}, status=400)
    except Exception as e:
        return _json({"ok": False, "error": str(e)[:500]}, status=400)
    return _json({"ok": True})


@require_http_methods(["POST"])
@permission_required("view_warehouse")
def api_project_materials_writeoff(request: HttpRequest, pk: int) -> JsonResponse:
    err, data = _project_and_warehouses(request, pk)
    if err:
        return err
    project, warehouses, wh_ids = data
    company = project.company
    if not _can_edit(request.user, company):
        return _json({"ok": False, "error": "forbidden"}, status=403)
    data = json.loads(request.body or b"{}")
    material = get_object_or_404(Material, pk=int(data.get("material_id")), company=company)
    warehouse = get_object_or_404(Warehouse, pk=int(data.get("warehouse_id")), company=company, is_deleted=False)
    if warehouse.id not in wh_ids:
        return _json({"ok": False, "error": "invalid_warehouse"}, status=400)
    qty = _parse_decimal(data.get("quantity"))
    if not qty or qty <= 0:
        return _json({"ok": False, "error": "bad_quantity"}, status=400)
    reason = (data.get("writeoff_reason") or "").strip()[:20]
    if reason not in dict(StockMovement.WRITEOFF_REASON_CHOICES):
        return _json({"ok": False, "error": "bad_reason"}, status=400)
    try:
        apply_writeoff(
            material=material,
            warehouse=warehouse,
            quantity=qty,
            date=_movement_date(data),
            comment=(data.get("comment") or "").strip()[:500],
            project=None,
            writeoff_reason=reason,
            user=request.user,
        )
    except Stock.DoesNotExist:
        return _json({"ok": False, "error": "no_stock_row"}, status=400)
    except Exception as e:
        return _json({"ok": False, "error": str(e)[:500]}, status=400)
    return _json({"ok": True})
