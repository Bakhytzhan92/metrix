"""Workflow снабжения: согласование, заказы, закупка, склад, журнал."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Prefetch, Q
from django.utils import timezone

from .models import (
    OffEstimateSupplyRequest,
    OffEstimateSupplyRequestItem,
    SupplyOrder,
    SupplyOrderItem,
    SupplyRequest,
    SupplyWorkflowLog,
    Warehouse,
)
from .warehouse_services import apply_incoming


def log_supply_event(
    *,
    company,
    action: str,
    user,
    project=None,
    supply_request=None,
    off_estimate_request=None,
    supply_order=None,
    comment: str = "",
) -> SupplyWorkflowLog:
    return SupplyWorkflowLog.objects.create(
        company=company,
        project=project,
        supply_request=supply_request,
        off_estimate_request=off_estimate_request,
        supply_order=supply_order,
        action=action,
        comment=(comment or "")[:2000],
        user=user,
    )


def log_estimate_request_created(req: SupplyRequest, user) -> None:
    log_supply_event(
        company=req.company,
        project=req.project,
        supply_request=req,
        action=SupplyWorkflowLog.ACTION_CREATED,
        user=user,
        comment=f"Заявка: {req.resource.name}, кол-во {req.quantity}",
    )


def log_off_estimate_request_created(req: OffEstimateSupplyRequest, user) -> None:
    log_supply_event(
        company=req.company,
        project=req.project,
        off_estimate_request=req,
        action=SupplyWorkflowLog.ACTION_CREATED,
        user=user,
        comment=f"Заявка {req.number}, позиций: {req.items.count()}",
    )


def get_workflow_logs_for_request(*, supply_request=None, off_estimate_request=None):
    if supply_request:
        return supply_request.workflow_logs.select_related("user").all()
    if off_estimate_request:
        return off_estimate_request.workflow_logs.select_related("user").all()
    return SupplyWorkflowLog.objects.none()


def get_workflow_logs_for_order(order: SupplyOrder):
    q = Q(supply_order=order)
    if order.off_estimate_request_id:
        q |= Q(off_estimate_request_id=order.off_estimate_request_id)
    req_ids = list(
        order.items.filter(request_id__isnull=False).values_list("request_id", flat=True)
    )
    if req_ids:
        q |= Q(supply_request_id__in=req_ids)
    return (
        SupplyWorkflowLog.objects.filter(q)
        .select_related("user")
        .order_by("-created_at", "-id")
        .distinct()
    )


def _sync_request_status_from_order(order: SupplyOrder) -> None:
    status_map = {
        SupplyOrder.PROCUREMENT_PENDING: SupplyRequest.STATUS_APPROVED,
        SupplyOrder.PROCUREMENT_IN_PROGRESS: SupplyRequest.STATUS_IN_PROGRESS,
        SupplyOrder.PROCUREMENT_PARTIAL: SupplyRequest.STATUS_PARTIAL,
        SupplyOrder.PROCUREMENT_PURCHASED: SupplyRequest.STATUS_PURCHASED,
        SupplyOrder.PROCUREMENT_CANCELLED: SupplyRequest.STATUS_CANCELLED,
    }
    req_status = status_map.get(order.procurement_status)
    if not req_status:
        return
    if order.off_estimate_request_id:
        OffEstimateSupplyRequest.objects.filter(pk=order.off_estimate_request_id).update(
            status=req_status
        )
    for item in order.items.select_related("request").all():
        if item.request_id:
            SupplyRequest.objects.filter(pk=item.request_id).update(status=req_status)


def recalc_order_procurement_status(order: SupplyOrder) -> str:
    items = list(order.items.all())
    if not items:
        return order.procurement_status
    if order.procurement_status == SupplyOrder.PROCUREMENT_CANCELLED:
        return order.procurement_status

    all_zero_purchased = all((i.quantity_purchased or 0) <= 0 for i in items)
    all_complete = all(i.quantity_remainder <= 0 for i in items)
    any_purchased = any((i.quantity_purchased or 0) > 0 for i in items)

    if all_complete and any_purchased:
        new_status = SupplyOrder.PROCUREMENT_PURCHASED
        action = SupplyWorkflowLog.ACTION_FULL_PURCHASE
    elif any_purchased and not all_complete:
        new_status = SupplyOrder.PROCUREMENT_PARTIAL
        action = SupplyWorkflowLog.ACTION_PARTIAL_PURCHASE
    elif order.procurement_status == SupplyOrder.PROCUREMENT_IN_PROGRESS and all_zero_purchased:
        new_status = SupplyOrder.PROCUREMENT_IN_PROGRESS
        action = None
    else:
        return order.procurement_status

    if new_status != order.procurement_status:
        order.procurement_status = new_status
        order.save(update_fields=["procurement_status"])
        _sync_request_status_from_order(order)
        if action:
            log_supply_event(
                company=order.company,
                project=order.project,
                supply_order=order,
                off_estimate_request=order.off_estimate_request,
                action=action,
                user=None,
                comment=order.get_procurement_status_display(),
            )
    return order.procurement_status


@transaction.atomic
def approve_supply_request(
    *,
    supply_request: SupplyRequest | None = None,
    off_estimate_request: OffEstimateSupplyRequest | None = None,
    user,
    supplier: str = "",
) -> SupplyOrder:
    if supply_request:
        if supply_request.status != SupplyRequest.STATUS_APPROVAL:
            raise ValueError("not_on_approval")
        if supply_request.supply_order_id:
            raise ValueError("already_has_order")
        order = _create_order_from_estimate_request(supply_request, user, supplier)
        supply_request.status = SupplyRequest.STATUS_APPROVED
        supply_request.approved_by = user
        supply_request.approved_at = timezone.now()
        supply_request.supply_order = order
        supply_request.save(
            update_fields=["status", "approved_by", "approved_at", "supply_order"]
        )
        log_supply_event(
            company=supply_request.company,
            project=supply_request.project,
            supply_request=supply_request,
            supply_order=order,
            action=SupplyWorkflowLog.ACTION_APPROVED,
            user=user,
        )
        log_supply_event(
            company=order.company,
            project=order.project,
            supply_order=order,
            supply_request=supply_request,
            action=SupplyWorkflowLog.ACTION_PROCUREMENT_STARTED,
            user=user,
            comment="Создан заказ после согласования",
        )
        return order

    if off_estimate_request:
        if off_estimate_request.status != OffEstimateSupplyRequest.STATUS_APPROVAL:
            raise ValueError("not_on_approval")
        if SupplyOrder.objects.filter(off_estimate_request=off_estimate_request).exists():
            raise ValueError("already_has_order")
        order = _create_order_from_off_estimate(off_estimate_request, user, supplier)
        off_estimate_request.status = OffEstimateSupplyRequest.STATUS_APPROVED
        off_estimate_request.approved_by = user
        off_estimate_request.approved_at = timezone.now()
        off_estimate_request.save(
            update_fields=["status", "approved_by", "approved_at"]
        )
        log_supply_event(
            company=off_estimate_request.company,
            project=off_estimate_request.project,
            off_estimate_request=off_estimate_request,
            supply_order=order,
            action=SupplyWorkflowLog.ACTION_APPROVED,
            user=user,
        )
        log_supply_event(
            company=order.company,
            project=order.project,
            supply_order=order,
            off_estimate_request=off_estimate_request,
            action=SupplyWorkflowLog.ACTION_PROCUREMENT_STARTED,
            user=user,
            comment="Создан заказ после согласования",
        )
        return order

    raise ValueError("no_request")


@transaction.atomic
def reject_supply_request(
    *,
    supply_request: SupplyRequest | None = None,
    off_estimate_request: OffEstimateSupplyRequest | None = None,
    user,
    reason: str,
) -> None:
    reason = (reason or "").strip()
    if not reason:
        raise ValueError("reason_required")

    if supply_request:
        if supply_request.status != SupplyRequest.STATUS_APPROVAL:
            raise ValueError("not_on_approval")
        supply_request.status = SupplyRequest.STATUS_CANCELLED
        supply_request.rejection_reason = reason[:2000]
        supply_request.approved_by = user
        supply_request.approved_at = timezone.now()
        supply_request.save(
            update_fields=["status", "rejection_reason", "approved_by", "approved_at"]
        )
        log_supply_event(
            company=supply_request.company,
            project=supply_request.project,
            supply_request=supply_request,
            action=SupplyWorkflowLog.ACTION_REJECTED,
            user=user,
            comment=reason,
        )
        return

    if off_estimate_request:
        if off_estimate_request.status != OffEstimateSupplyRequest.STATUS_APPROVAL:
            raise ValueError("not_on_approval")
        off_estimate_request.status = OffEstimateSupplyRequest.STATUS_CANCELLED
        off_estimate_request.rejection_reason = reason[:2000]
        off_estimate_request.approved_by = user
        off_estimate_request.approved_at = timezone.now()
        off_estimate_request.save(
            update_fields=["status", "rejection_reason", "approved_by", "approved_at"]
        )
        log_supply_event(
            company=off_estimate_request.company,
            project=off_estimate_request.project,
            off_estimate_request=off_estimate_request,
            action=SupplyWorkflowLog.ACTION_REJECTED,
            user=user,
            comment=reason,
        )
        return

    raise ValueError("no_request")


def _finalize_new_order_procurement(order: SupplyOrder) -> None:
    """Позиции заказа считаются полностью закупленными (без ручного ввода в UI)."""
    for item in order.items.select_related("request", "off_estimate_item").all():
        qty = item.quantity or Decimal("0")
        item.quantity_purchased = qty
        item.save(update_fields=["quantity_purchased"])
        if item.request_id:
            SupplyRequest.objects.filter(pk=item.request_id).update(
                quantity_received=qty
            )
        if item.off_estimate_item_id:
            OffEstimateSupplyRequestItem.objects.filter(
                pk=item.off_estimate_item_id
            ).update(quantity_purchased=qty)
    order.procurement_status = SupplyOrder.PROCUREMENT_PURCHASED
    order.save(update_fields=["procurement_status"])
    _sync_request_status_from_order(order)


def _create_order_from_estimate_request(
    req: SupplyRequest, user, supplier: str
) -> SupplyOrder:
    order = SupplyOrder.objects.create(
        company=req.company,
        project=req.project,
        supplier=(supplier or req.supplier_name or "—")[:255],
        status=SupplyOrder.STATUS_NEW,
        procurement_status=SupplyOrder.PROCUREMENT_PENDING,
        payment_status=SupplyOrder.PAYMENT_DRAFT,
    )
    SupplyOrderItem.objects.create(
        order=order,
        request=req,
        quantity=req.quantity,
        quantity_purchased=Decimal("0"),
        price_fact=req.price_plan or Decimal("0"),
    )
    order.recalc_total()
    order.save(update_fields=["total_amount"])
    log_supply_event(
        company=order.company,
        project=order.project,
        supply_order=order,
        supply_request=req,
        action=SupplyWorkflowLog.ACTION_CREATED,
        user=user,
        comment=f"Заказ по заявке: {req.resource.name}",
    )
    _finalize_new_order_procurement(order)
    return order


def _create_order_from_off_estimate(
    req: OffEstimateSupplyRequest, user, supplier: str
) -> SupplyOrder:
    order = SupplyOrder.objects.create(
        company=req.company,
        project=req.project,
        supplier=(supplier or "—")[:255],
        status=SupplyOrder.STATUS_NEW,
        procurement_status=SupplyOrder.PROCUREMENT_PENDING,
        payment_status=SupplyOrder.PAYMENT_DRAFT,
        off_estimate_request=req,
    )
    items = req.items.order_by("sort_order", "id")
    for line in items:
        SupplyOrderItem.objects.create(
            order=order,
            off_estimate_item=line,
            line_name=line.material_name,
            line_unit=line.unit,
            quantity=line.quantity,
            quantity_purchased=Decimal("0"),
            price_fact=Decimal("0"),
        )
    order.recalc_total()
    order.save(update_fields=["total_amount"])
    log_supply_event(
        company=order.company,
        project=order.project,
        supply_order=order,
        off_estimate_request=req,
        action=SupplyWorkflowLog.ACTION_CREATED,
        user=user,
        comment=f"Заказ по заявке {req.number}",
    )
    _finalize_new_order_procurement(order)
    return order


@transaction.atomic
def start_order_procurement(order: SupplyOrder, *, user, supplier: str = "") -> SupplyOrder:
    if order.procurement_status != SupplyOrder.PROCUREMENT_PENDING:
        raise ValueError("invalid_status")
    if supplier:
        order.supplier = supplier[:255]
    order.procurement_status = SupplyOrder.PROCUREMENT_IN_PROGRESS
    order.save(update_fields=["procurement_status", "supplier"])
    _sync_request_status_from_order(order)
    log_supply_event(
        company=order.company,
        project=order.project,
        supply_order=order,
        off_estimate_request=order.off_estimate_request,
        action=SupplyWorkflowLog.ACTION_PROCUREMENT_STARTED,
        user=user,
        comment=f"Поставщик: {order.supplier or '—'}",
    )
    return order


@transaction.atomic
def update_order_item_purchased(
    item: SupplyOrderItem, *, quantity_purchased: Decimal, user
) -> SupplyOrderItem:
    order = item.order
    if order.procurement_status not in (
        SupplyOrder.PROCUREMENT_IN_PROGRESS,
        SupplyOrder.PROCUREMENT_PARTIAL,
        SupplyOrder.PROCUREMENT_PENDING,
    ):
        raise ValueError("invalid_status")
    if quantity_purchased < 0:
        quantity_purchased = Decimal("0")
    max_q = item.quantity or Decimal("0")
    if quantity_purchased > max_q:
        quantity_purchased = max_q

    item.quantity_purchased = quantity_purchased
    item.save()

    if item.request_id:
        SupplyRequest.objects.filter(pk=item.request_id).update(
            quantity_received=quantity_purchased
        )
    if item.off_estimate_item_id:
        OffEstimateSupplyRequestItem.objects.filter(pk=item.off_estimate_item_id).update(
            quantity_purchased=quantity_purchased
        )

    if order.procurement_status == SupplyOrder.PROCUREMENT_PENDING:
        order.procurement_status = SupplyOrder.PROCUREMENT_IN_PROGRESS
        order.save(update_fields=["procurement_status"])

    recalc_order_procurement_status(order)
    return item


@transaction.atomic
def cancel_order(order: SupplyOrder, *, user, reason: str = "") -> SupplyOrder:
    if order.procurement_status == SupplyOrder.PROCUREMENT_PURCHASED:
        raise ValueError("already_purchased")
    order.procurement_status = SupplyOrder.PROCUREMENT_CANCELLED
    order.save(update_fields=["procurement_status"])
    _sync_request_status_from_order(order)
    log_supply_event(
        company=order.company,
        project=order.project,
        supply_order=order,
        action=SupplyWorkflowLog.ACTION_CANCELLED,
        user=user,
        comment=reason,
    )
    return order


@transaction.atomic
def transfer_order_to_warehouse(
    order: SupplyOrder, *, warehouse: Warehouse, user
) -> SupplyOrder:
    if order.procurement_status != SupplyOrder.PROCUREMENT_PURCHASED:
        raise ValueError("not_fully_purchased")
    if warehouse.company_id != order.company_id:
        raise ValueError("wrong_warehouse")
    if warehouse.is_deleted:
        raise ValueError("warehouse_deleted")

    for item in order.items.select_related("request", "off_estimate_item").all():
        if item.warehouse_received:
            continue
        qty = item.quantity_purchased or Decimal("0")
        if qty <= 0:
            raise ValueError("empty_purchase")
        name = item.display_name
        unit = item.display_unit
        from .models import Material

        material = Material.objects.filter(
            company=order.company, name=name
        ).first()
        if not material:
            material = Material.objects.create(
                company=order.company,
                name=name,
                unit=unit,
                category=Material.CATEGORY_MATERIAL,
                supplier=order.supplier or "",
                description=f"Заказ снабжения #{order.pk}",
            )
        apply_incoming(
            material=material,
            warehouse=warehouse,
            quantity=qty,
            price=item.price_fact or Decimal("0"),
            date=timezone.now().date(),
            comment=f"Заказ снабжения #{order.pk}",
            supplier=order.supplier or "",
            user=user,
        )
        item.material = material
        item.warehouse = warehouse
        item.warehouse_received = True
        item.warehouse_received_at = timezone.now()
        item.save(
            update_fields=[
                "material",
                "warehouse",
                "warehouse_received",
                "warehouse_received_at",
            ]
        )
        if item.off_estimate_item_id:
            OffEstimateSupplyRequestItem.objects.filter(
                pk=item.off_estimate_item_id
            ).update(
                material=material,
                warehouse=warehouse,
                warehouse_received=True,
                warehouse_received_at=timezone.now(),
            )

    log_supply_event(
        company=order.company,
        project=order.project,
        supply_order=order,
        action=SupplyWorkflowLog.ACTION_WAREHOUSE_TRANSFER,
        user=user,
        comment=f"Склад: {warehouse.name}",
    )
    return order


def list_pending_approval(project) -> dict:
    estimate_qs = (
        SupplyRequest.objects.filter(
            project=project, status=SupplyRequest.STATUS_APPROVAL
        )
        .select_related("resource", "created_by", "estimate_item", "estimate_item__section")
        .order_by("-created_at")
    )
    off_qs = (
        OffEstimateSupplyRequest.objects.filter(
            project=project, status=OffEstimateSupplyRequest.STATUS_APPROVAL
        )
        .select_related("created_by")
        .prefetch_related(
            Prefetch(
                "items",
                queryset=OffEstimateSupplyRequestItem.objects.order_by(
                    "sort_order", "id"
                ),
            )
        )
        .order_by("-created_at")
    )
    return {"estimate_requests": estimate_qs, "off_estimate_requests": off_qs}


def parse_purchased_qty(raw) -> Decimal:
    try:
        val = Decimal(str(raw).replace(",", "."))
    except (InvalidOperation, TypeError):
        raise ValueError("bad_quantity")
    if val < 0:
        val = Decimal("0")
    return val
