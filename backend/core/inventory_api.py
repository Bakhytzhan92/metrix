"""
JSON API инвентаря (ERP, этап 1). Требуется аутентификация и права на склады.
"""
from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from django.contrib.auth import get_user_model
from django.db.models import Count, Q, Sum
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods

from .access_utils import get_current_company, has_permission
from .inventory_numbering import allocate_inventory_number
from .inventory_qr import ensure_qr_image_file, qr_png_bytes, item_qr_target_url
from .inventory_services import (
    issue_inventory_to_user,
    log_inventory_action,
    mark_inventory_lost,
    mark_inventory_repair,
    return_inventory_from_user,
    set_inventory_status,
    transfer_inventory_item,
)
from .models import (
    CompanyUser,
    InventoryLog,
    Project,
    UserProfile,
    Warehouse,
    WarehouseInventoryItem,
)
from .rbac import permission_required


User = get_user_model()


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


def _company(request: HttpRequest):
    c = getattr(request, "current_company", None) or get_current_company(request.user)
    return c


def _can_edit(user, company) -> bool:
    return has_permission(user, company, "edit_warehouse")


def _is_platform_super_admin(user) -> bool:
    return UserProfile.objects.filter(user=user, is_super_admin=True).exists()


def _serialize_item(
    item: WarehouseInventoryItem,
    *,
    with_price: bool,
) -> dict[str, Any]:
    img = item.image.url if item.image else None
    qr = item.qr_image.url if item.qr_image else None
    data: dict[str, Any] = {
        "id": item.id,
        "name": item.name,
        "category": item.category,
        "inventory_number": item.inventory_number,
        "serial_number": item.serial_number,
        "status": item.status,
        "status_display": item.get_status_display(),
        "warehouse_id": item.warehouse_id,
        "warehouse_name": item.warehouse.name,
        "project_id": item.project_id,
        "responsible_user_id": item.responsible_user_id,
        "assigned_to_id": item.assigned_to_id,
        "purchase_date": str(item.purchase_date) if item.purchase_date else None,
        "warranty_until": str(item.warranty_until) if item.warranty_until else None,
        "description": item.description,
        "comment": item.comment,
        "issued_at": item.issued_at.isoformat() if item.issued_at else None,
        "return_due_at": str(item.return_due_at) if item.return_due_at else None,
        "available_from": str(item.available_from) if item.available_from else None,
        "image_url": img,
        "qr_url": qr,
        "updated_at": item.updated_at.isoformat(),
    }
    if with_price:
        data["purchase_price"] = str(item.purchase_price or 0)
    return data


@require_GET
@permission_required("view_warehouse")
def api_inventory_meta(request: HttpRequest) -> JsonResponse:
    company = _company(request)
    if not company:
        return _json({"ok": False, "error": "no_company"}, status=403)
    with_price = has_permission(request.user, company, "view_warehouse")
    users_qs = User.objects.filter(
        company_users__company=company,
        company_users__is_active=True,
    ).distinct().values("id", "username", "first_name", "last_name")[:500]
    users = [
        {
            "id": u["id"],
            "username": u["username"],
            "label": (
                (f'{u["first_name"]} {u["last_name"]}'.strip() or u["username"])
            ),
        }
        for u in users_qs
    ]
    warehouses = list(
        Warehouse.objects.filter(company=company, is_deleted=False)
        .order_by("name")
        .values("id", "name", "project_id")
    )
    projects = list(
        Project.objects.filter(company=company)
        .order_by("-created_at")
        .values("id", "name")[:200]
    )
    _status_skip = frozenset(
        {
            WarehouseInventoryItem.STATUS_ISSUED,
            WarehouseInventoryItem.STATUS_LOST,
        }
    )
    return _json(
        {
            "ok": True,
            "company_id": company.id,
            "inventory_prefix_hint": (company.inventory_prefix or "").strip(),
            "can_edit": _can_edit(request.user, company),
            "show_prices": with_price,
            "status_choices": [
                {"value": k, "label": str(v)}
                for k, v in WarehouseInventoryItem.STATUS_CHOICES
                if k not in _status_skip
            ],
            "category_choices": [
                {"value": k, "label": str(v)}
                for k, v in WarehouseInventoryItem.CATEGORY_CHOICES
            ],
            "warehouses": warehouses,
            "projects": projects,
            "users": users,
        }
    )


@require_GET
@permission_required("view_warehouse")
def api_inventory_warehouse_summary(request: HttpRequest) -> JsonResponse:
    company = _company(request)
    if not company:
        return _json({"ok": False, "error": "no_company"}, status=403)
    with_price = has_permission(request.user, company, "view_warehouse")
    qs = (
        Warehouse.objects.filter(company=company, is_deleted=False)
        .annotate(
            item_count=Count(
                "warehouse_inventory_items",
                filter=Q(warehouse_inventory_items__status__in=[
                    WarehouseInventoryItem.STATUS_FREE,
                    WarehouseInventoryItem.STATUS_IN_USE,
                    WarehouseInventoryItem.STATUS_ISSUED,
                    WarehouseInventoryItem.STATUS_REPAIR,
                    WarehouseInventoryItem.STATUS_LOST,
                ]),
            )
        )
    )
    if with_price:
        qs = qs.annotate(
            total_value=Sum(
                "warehouse_inventory_items__purchase_price",
                filter=Q(
                    warehouse_inventory_items__status__in=[
                        WarehouseInventoryItem.STATUS_FREE,
                        WarehouseInventoryItem.STATUS_IN_USE,
                        WarehouseInventoryItem.STATUS_ISSUED,
                        WarehouseInventoryItem.STATUS_REPAIR,
                    ]
                ),
            )
        )
    rows = []
    for w in qs.order_by("name"):
        row = {
            "id": w.id,
            "name": w.name,
            "project_id": w.project_id,
            "item_count": w.item_count,
        }
        if with_price:
            row["total_value"] = str(w.total_value or Decimal("0"))
        rows.append(row)
    return _json({"ok": True, "warehouses": rows})


@require_http_methods(["GET", "POST"])
@permission_required("view_warehouse")
def api_inventory_items(request: HttpRequest) -> JsonResponse:
    company = _company(request)
    if not company:
        return _json({"ok": False, "error": "no_company"}, status=403)
    with_price = has_permission(request.user, company, "view_warehouse")
    if request.method == "GET":
        q = (request.GET.get("q") or "").strip()
        wh_id = request.GET.get("warehouse")
        st = request.GET.get("status")
        cat = request.GET.get("category")
        proj = request.GET.get("project")
        items = WarehouseInventoryItem.objects.filter(company=company).select_related(
            "warehouse", "project", "responsible_user", "assigned_to"
        )
        if q:
            items = items.filter(
                Q(name__icontains=q)
                | Q(inventory_number__icontains=q)
                | Q(serial_number__icontains=q)
            )
        if wh_id and wh_id.isdigit():
            items = items.filter(warehouse_id=int(wh_id))
        if st:
            items = items.filter(status=st)
        if cat:
            items = items.filter(category=cat)
        if proj and proj.isdigit():
            items = items.filter(project_id=int(proj))
        data = [_serialize_item(i, with_price=with_price) for i in items.order_by("-updated_at")[:1000]]
        return _json({"ok": True, "items": data})

    if not _can_edit(request.user, company):
        return _json({"ok": False, "error": "forbidden"}, status=403)
    if request.content_type and "multipart/form-data" in request.content_type:
        payload = request.POST
        image = request.FILES.get("image")
    else:
        payload = json.loads(request.body or b"{}")
        image = None
    name = (payload.get("name") or "").strip()
    if not name:
        return _json({"ok": False, "error": "name_required"}, status=400)
    wh_id = payload.get("warehouse") or payload.get("warehouse_id")
    warehouse = get_object_or_404(Warehouse, pk=int(wh_id), company=company, is_deleted=False)
    category = payload.get("category") or WarehouseInventoryItem.CATEGORY_OTHER
    if category not in dict(WarehouseInventoryItem.CATEGORY_CHOICES):
        category = WarehouseInventoryItem.CATEGORY_OTHER
    inv_num = (payload.get("inventory_number") or "").strip()
    if not inv_num:
        inv_num = allocate_inventory_number(company, category)
    item = WarehouseInventoryItem(
        company=company,
        warehouse=warehouse,
        name=name,
        category=category,
        inventory_number=inv_num,
        serial_number=(payload.get("serial_number") or "").strip()[:128],
        status=payload.get("status") or WarehouseInventoryItem.STATUS_FREE,
        purchase_price=_parse_decimal(payload.get("purchase_price")) or Decimal("0"),
        purchase_date=_parse_date(payload.get("purchase_date")),
        warranty_until=_parse_date(payload.get("warranty_until")),
        description=(payload.get("description") or "").strip(),
        comment=(payload.get("comment") or "").strip(),
    )
    if item.status not in dict(WarehouseInventoryItem.STATUS_CHOICES):
        item.status = WarehouseInventoryItem.STATUS_FREE
    elif item.status in (
        WarehouseInventoryItem.STATUS_ISSUED,
        WarehouseInventoryItem.STATUS_LOST,
    ):
        item.status = WarehouseInventoryItem.STATUS_FREE
    pu_id = payload.get("responsible_user_id") or payload.get("responsible_user")
    if pu_id and str(pu_id).isdigit():
        uid = int(pu_id)
        if User.objects.filter(company_users__company=company, id=uid).exists():
            item.responsible_user_id = uid
    pr_id = payload.get("project_id") or payload.get("project")
    if pr_id and str(pr_id).isdigit():
        pid = int(pr_id)
        if Project.objects.filter(company=company, pk=pid).exists():
            item.project_id = pid
    if image:
        item.image = image
    item.save()
    log_inventory_action(item, InventoryLog.ACTION_CREATED, request.user, "Создан инвентарь")
    ensure_qr_image_file(item, request)
    item.refresh_from_db()
    return _json({"ok": True, "item": _serialize_item(item, with_price=with_price)}, status=201)


@require_http_methods(["GET", "PATCH"])
@permission_required("view_warehouse")
def api_inventory_item_detail(request: HttpRequest, pk: int) -> JsonResponse:
    company = _company(request)
    if not company:
        return _json({"ok": False, "error": "no_company"}, status=403)
    item = get_object_or_404(
        WarehouseInventoryItem.objects.select_related("warehouse", "project"),
        pk=pk,
        company=company,
    )
    with_price = has_permission(request.user, company, "view_warehouse")
    if request.method == "GET":
        logs = [
            {
                "id": lg.id,
                "action": lg.action,
                "action_display": lg.get_action_display(),
                "description": lg.description,
                "details": lg.details,
                "created_at": lg.created_at.isoformat(),
                "user_id": lg.user_id,
                "username": lg.user.get_username() if lg.user else None,
            }
            for lg in item.logs.select_related("user").order_by("-created_at")[:100]
        ]
        return _json(
            {
                "ok": True,
                "item": _serialize_item(item, with_price=with_price),
                "history": logs,
            }
        )
    if not _can_edit(request.user, company):
        return _json({"ok": False, "error": "forbidden"}, status=403)
    data = json.loads(request.body or b"{}")
    status_new = data.get("status")

    if "name" in data:
        item.name = (data["name"] or "").strip() or item.name
    if "category" in data and data["category"] in dict(WarehouseInventoryItem.CATEGORY_CHOICES):
        item.category = data["category"]
    if "serial_number" in data:
        item.serial_number = (data["serial_number"] or "")[:128]
    if "description" in data:
        item.description = (data["description"] or "").strip()
    if "comment" in data:
        item.comment = (data["comment"] or "").strip()
    if "purchase_price" in data:
        item.purchase_price = _parse_decimal(data["purchase_price"]) or item.purchase_price
    if "purchase_date" in data:
        item.purchase_date = _parse_date(data.get("purchase_date"))
    if "warranty_until" in data:
        item.warranty_until = _parse_date(data.get("warranty_until"))
    if "inventory_number" in data and _is_platform_super_admin(request.user):
        item.inventory_number = (data["inventory_number"] or "").strip()[:100]

    if "warehouse_id" in data and str(data["warehouse_id"]).isdigit():
        if status_new != WarehouseInventoryItem.STATUS_WRITTEN_OFF:
            wh = get_object_or_404(
                Warehouse, pk=int(data["warehouse_id"]), company=company, is_deleted=False
            )
            if wh.id != item.warehouse_id:
                transfer_inventory_item(
                    item,
                    wh,
                    request.user,
                    comment=(data.get("move_comment") or data.get("comment") or "Карточка")[:500],
                )

    if "project_id" in data:
        pid = data["project_id"]
        item.project_id = int(pid) if pid and str(pid).isdigit() else None
        if item.project_id and not Project.objects.filter(company=company, pk=item.project_id).exists():
            item.project_id = None
    if "responsible_user_id" in data:
        rid = data["responsible_user_id"]
        if rid and str(rid).isdigit():
            if User.objects.filter(id=int(rid), company_users__company=company).exists():
                item.responsible_user_id = int(rid)
        else:
            item.responsible_user_id = None

    item.save()

    if status_new and status_new in dict(WarehouseInventoryItem.STATUS_CHOICES):
        if status_new not in (
            WarehouseInventoryItem.STATUS_ISSUED,
            WarehouseInventoryItem.STATUS_LOST,
        ):
            set_inventory_status(
                item,
                status_new,
                request.user,
                available_from=_parse_date(data.get("available_from")),
                description=(data.get("status_comment") or "").strip(),
            )
            item.refresh_from_db()

    log_inventory_action(item, InventoryLog.ACTION_UPDATED, request.user, "Изменён через API")
    item.refresh_from_db()
    return _json({"ok": True, "item": _serialize_item(item, with_price=with_price)})


def _item_action(
    request: HttpRequest,
    pk: int,
    *,
    handler,
) -> JsonResponse:
    company = _company(request)
    if not company or not _can_edit(request.user, company):
        return _json({"ok": False, "error": "forbidden"}, status=403)
    item = get_object_or_404(WarehouseInventoryItem, pk=pk, company=company)
    data = json.loads(request.body or b"{}") if request.body else {}
    try:
        handler(item, request.user, data)
    except Exception as e:
        return _json({"ok": False, "error": str(e)[:500]}, status=400)
    with_price = has_permission(request.user, company, "view_warehouse")
    item.refresh_from_db()
    return _json({"ok": True, "item": _serialize_item(item, with_price=with_price)})


@require_http_methods(["POST"])
@permission_required("view_warehouse")
def api_inventory_item_move(request: HttpRequest, pk: int) -> JsonResponse:
    def run(item, user, data):
        wh_id = data.get("to_warehouse_id") or data.get("warehouse_id")
        comment = (data.get("comment") or "").strip()[:500]
        wh = get_object_or_404(Warehouse, pk=int(wh_id), company=item.company, is_deleted=False)
        transfer_inventory_item(item, wh, user, comment=comment)

    return _item_action(request, pk, handler=run)


@require_http_methods(["POST"])
@permission_required("view_warehouse")
def api_inventory_item_issue(request: HttpRequest, pk: int) -> JsonResponse:
    def run(item, user, data):
        uid = data.get("user_id")
        to_u = get_object_or_404(User, pk=int(uid))
        if not CompanyUser.objects.filter(user=to_u, company=item.company, is_active=True).exists():
            raise ValueError("Пользователь не в компании")
        issue_inventory_to_user(
            item,
            to_u,
            user,
            comment=(data.get("comment") or "").strip(),
            return_due_at=_parse_date(data.get("return_due_at")),
        )

    return _item_action(request, pk, handler=run)


@require_http_methods(["POST"])
@permission_required("view_warehouse")
def api_inventory_item_return(request: HttpRequest, pk: int) -> JsonResponse:
    def run(item, user, data):
        st = data.get("status") or WarehouseInventoryItem.STATUS_FREE
        if st not in (WarehouseInventoryItem.STATUS_FREE, WarehouseInventoryItem.STATUS_IN_USE):
            st = WarehouseInventoryItem.STATUS_FREE
        return_inventory_from_user(
            item,
            user,
            comment=(data.get("comment") or "").strip(),
            new_status=st,
        )

    return _item_action(request, pk, handler=run)


@require_http_methods(["POST"])
@permission_required("view_warehouse")
def api_inventory_item_repair(request: HttpRequest, pk: int) -> JsonResponse:
    def run(item, user, data):
        mark_inventory_repair(item, user, comment=(data.get("comment") or "").strip())

    return _item_action(request, pk, handler=run)


@require_http_methods(["POST"])
@permission_required("view_warehouse")
def api_inventory_item_lost(request: HttpRequest, pk: int) -> JsonResponse:
    def run(item, user, data):
        mark_inventory_lost(item, user, comment=(data.get("comment") or "").strip())

    return _item_action(request, pk, handler=run)


@require_http_methods(["POST"])
@permission_required("view_warehouse")
def api_inventory_item_writeoff(request: HttpRequest, pk: int) -> JsonResponse:
    def run(item, user, data):
        set_inventory_status(
            item,
            WarehouseInventoryItem.STATUS_WRITTEN_OFF,
            user,
            description=(data.get("comment") or "").strip(),
        )

    return _item_action(request, pk, handler=run)


@require_GET
@permission_required("view_warehouse")
def api_inventory_item_qr(request: HttpRequest, pk: int) -> HttpResponse:
    company = _company(request)
    if not company:
        return HttpResponse(status=403)
    item = get_object_or_404(WarehouseInventoryItem, pk=pk, company=company)
    ensure_qr_image_file(item, request)
    data = qr_png_bytes(item_qr_target_url(request, item.pk))
    return HttpResponse(data, content_type="image/png")


@require_GET
@permission_required("view_warehouse")
def api_inventory_history(request: HttpRequest) -> JsonResponse:
    company = _company(request)
    if not company:
        return _json({"ok": False, "error": "no_company"}, status=403)
    item_id = request.GET.get("item_id")
    qs = InventoryLog.objects.filter(item__company=company).select_related("item", "user")
    if item_id and item_id.isdigit():
        qs = qs.filter(item_id=int(item_id))
    logs = qs.order_by("-created_at")[:500]
    return _json(
        {
            "ok": True,
            "entries": [
                {
                    "id": lg.id,
                    "item_id": lg.item_id,
                    "item_name": lg.item.name,
                    "inventory_number": lg.item.inventory_number,
                    "action": lg.action,
                    "action_display": lg.get_action_display(),
                    "description": lg.description,
                    "details": lg.details,
                    "created_at": lg.created_at.isoformat(),
                    "user_id": lg.user_id,
                    "username": lg.user.get_username() if lg.user else None,
                }
                for lg in logs
            ],
        }
    )


@require_http_methods(["GET", "POST"])
@permission_required("view_warehouse")
def api_inventory_warehouses(request: HttpRequest) -> JsonResponse:
    company = _company(request)
    if not company:
        return _json({"ok": False, "error": "no_company"}, status=403)
    if request.method == "GET":
        rows = Warehouse.objects.filter(company=company, is_deleted=False).order_by("name")
        return _json(
            {
                "ok": True,
                "warehouses": [
                    {"id": w.id, "name": w.name, "location": w.location, "project_id": w.project_id}
                    for w in rows
                ],
            }
        )
    if not _can_edit(request.user, company):
        return _json({"ok": False, "error": "forbidden"}, status=403)
    data = json.loads(request.body or b"{}")
    name = (data.get("name") or "").strip()
    if not name:
        return _json({"ok": False, "error": "name_required"}, status=400)
    w = Warehouse.objects.create(
        company=company,
        name=name,
        location=(data.get("location") or "").strip()[:255],
        project_id=int(data["project_id"]) if data.get("project_id") and str(data["project_id"]).isdigit() else None,
    )
    return _json({"ok": True, "warehouse": {"id": w.id, "name": w.name}}, status=201)


@require_http_methods(["PATCH", "DELETE"])
@permission_required("view_warehouse")
def api_inventory_warehouse_detail(request: HttpRequest, pk: int) -> JsonResponse:
    company = _company(request)
    if not company:
        return _json({"ok": False, "error": "no_company"}, status=403)
    wh = get_object_or_404(Warehouse, pk=pk, company=company)
    if not _can_edit(request.user, company):
        return _json({"ok": False, "error": "forbidden"}, status=403)
    if request.method == "DELETE":
        wh.is_deleted = True
        wh.save(update_fields=["is_deleted"])
        return _json({"ok": True})
    data = json.loads(request.body or b"{}")
    if "name" in data and (data["name"] or "").strip():
        wh.name = (data["name"] or "").strip()[:255]
    if "location" in data:
        wh.location = (data["location"] or "")[:255]
    wh.save()
    return _json({"ok": True, "warehouse": {"id": wh.id, "name": wh.name}})
