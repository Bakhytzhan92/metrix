"""Согласование оплаты заказов снабжения."""
from __future__ import annotations

import os
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Max, Prefetch
from django.utils import timezone

from .models import SupplyOrder, SupplyOrderDocument, SupplyWorkflowLog
from .supply_workflow_services import log_supply_event, mark_order_fully_purchased

ALLOWED_DOC_EXTENSIONS = frozenset(
    {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".jpg", ".jpeg", ".png"}
)
ALLOWED_POA_EXTENSIONS = frozenset({".pdf", ".doc", ".docx", ".xls", ".xlsx"})


def _parse_decimal(raw) -> Decimal:
    try:
        val = Decimal(str(raw).replace(",", ".").replace(" ", ""))
    except (InvalidOperation, TypeError):
        raise ValueError("bad_amount")
    if val < 0:
        raise ValueError("bad_amount")
    return val


def _validate_upload(file) -> None:
    if not file:
        raise ValueError("no_file")
    ext = os.path.splitext(file.name or "")[1].lower()
    if ext not in ALLOWED_DOC_EXTENSIONS:
        raise ValueError("bad_extension")


def _validate_poa_upload(file) -> None:
    if not file:
        raise ValueError("no_file")
    ext = os.path.splitext(file.name or "")[1].lower()
    if ext not in ALLOWED_POA_EXTENSIONS:
        raise ValueError("bad_extension")


def get_current_document(order: SupplyOrder, doc_type: str):
    return (
        order.documents.filter(doc_type=doc_type)
        .order_by("-version", "-id")
        .first()
    )


def get_document_history(order: SupplyOrder, doc_type: str):
    return order.documents.filter(doc_type=doc_type).order_by("-version", "-id")


@transaction.atomic
def upload_payment_proof(
    order: SupplyOrder,
    *,
    user,
    uploaded_file,
) -> SupplyOrderDocument:
    _validate_upload(uploaded_file)
    last = (
        order.documents.filter(doc_type=SupplyOrderDocument.DOC_PAYMENT_PROOF)
        .aggregate(m=Max("version"))
        .get("m")
        or 0
    )
    doc = SupplyOrderDocument.objects.create(
        order=order,
        doc_type=SupplyOrderDocument.DOC_PAYMENT_PROOF,
        file=uploaded_file,
        version=last + 1,
        uploaded_by=user,
    )
    log_supply_event(
        company=order.company,
        project=order.project,
        supply_order=order,
        action=SupplyWorkflowLog.ACTION_TRANSFERRED_TO_FINANCE,
        user=user,
        comment=f"Платёжка v{doc.version} загружена в финансах",
    )
    return doc


@transaction.atomic
def upload_power_of_attorney(
    order: SupplyOrder,
    *,
    user,
    uploaded_file,
) -> SupplyOrderDocument:
    if order.payment_status not in (
        SupplyOrder.PAYMENT_AWAITING,
        SupplyOrder.PAYMENT_PARTIAL,
        SupplyOrder.PAYMENT_PAID,
    ):
        raise ValueError("not_in_payment_queue")
    _validate_poa_upload(uploaded_file)
    last = (
        order.documents.filter(doc_type=SupplyOrderDocument.DOC_POA)
        .aggregate(m=Max("version"))
        .get("m")
        or 0
    )
    doc = SupplyOrderDocument.objects.create(
        order=order,
        doc_type=SupplyOrderDocument.DOC_POA,
        file=uploaded_file,
        version=last + 1,
        uploaded_by=user,
    )
    log_supply_event(
        company=order.company,
        project=order.project,
        supply_order=order,
        action=SupplyWorkflowLog.ACTION_TRANSFERRED_TO_FINANCE,
        user=user,
        comment=f"Доверенность v{doc.version} загружена в финансах",
    )
    return doc


@transaction.atomic
def update_order_procurement_info(
    order: SupplyOrder,
    *,
    user,
    supplier: str = "",
    purchase_amount_raw=None,
    planned_delivery_date=None,
    procurement_note: str = "",
) -> SupplyOrder:
    if order.payment_status not in (
        SupplyOrder.PAYMENT_DRAFT,
        SupplyOrder.PAYMENT_REJECTED,
    ):
        raise ValueError("not_editable")
    if order.procurement_status == SupplyOrder.PROCUREMENT_CANCELLED:
        raise ValueError("cancelled")

    fields = []
    if supplier is not None:
        order.supplier = (supplier or "").strip()[:255]
        fields.append("supplier")
    if purchase_amount_raw is not None and str(purchase_amount_raw).strip() != "":
        order.purchase_amount = _parse_decimal(purchase_amount_raw)
        fields.append("purchase_amount")
    if planned_delivery_date is not None:
        order.planned_delivery_date = planned_delivery_date
        fields.append("planned_delivery_date")
    if procurement_note is not None:
        order.procurement_note = (procurement_note or "")[:5000]
        fields.append("procurement_note")
    if fields:
        order.save(update_fields=fields)
    return order


@transaction.atomic
def upload_order_document(
    order: SupplyOrder,
    *,
    user,
    doc_type: str,
    uploaded_file,
) -> SupplyOrderDocument:
    if order.payment_status not in (
        SupplyOrder.PAYMENT_DRAFT,
        SupplyOrder.PAYMENT_REJECTED,
    ):
        raise ValueError("not_editable")
    if doc_type not in (SupplyOrderDocument.DOC_KP, SupplyOrderDocument.DOC_INVOICE):
        raise ValueError("bad_type")
    _validate_upload(uploaded_file)

    last = (
        order.documents.filter(doc_type=doc_type)
        .aggregate(m=Max("version"))
        .get("m")
        or 0
    )
    doc = SupplyOrderDocument.objects.create(
        order=order,
        doc_type=doc_type,
        file=uploaded_file,
        version=last + 1,
        uploaded_by=user,
    )
    action = (
        SupplyWorkflowLog.ACTION_KP_UPLOADED
        if doc_type == SupplyOrderDocument.DOC_KP
        else SupplyWorkflowLog.ACTION_INVOICE_UPLOADED
    )
    log_supply_event(
        company=order.company,
        project=order.project,
        supply_order=order,
        action=action,
        user=user,
        comment=f"{doc.get_doc_type_display()}, версия {doc.version}",
    )
    return doc


def _validate_ready_for_payment_approval(order: SupplyOrder) -> None:
    if not (order.supplier or "").strip():
        raise ValueError("supplier_required")
    if not order.purchase_amount or order.purchase_amount <= 0:
        raise ValueError("amount_required")
    has_kp = get_current_document(order, SupplyOrderDocument.DOC_KP)
    has_invoice = get_current_document(order, SupplyOrderDocument.DOC_INVOICE)
    if not has_kp and not has_invoice:
        raise ValueError("document_required")


@transaction.atomic
def submit_order_for_payment_approval(order: SupplyOrder, *, user) -> SupplyOrder:
    if order.procurement_status == SupplyOrder.PROCUREMENT_CANCELLED:
        raise ValueError("cancelled")
    if order.payment_status not in (
        SupplyOrder.PAYMENT_DRAFT,
        SupplyOrder.PAYMENT_REJECTED,
    ):
        raise ValueError("invalid_status")
    _validate_ready_for_payment_approval(order)

    is_resubmit = order.payment_status == SupplyOrder.PAYMENT_REJECTED
    order.payment_status = SupplyOrder.PAYMENT_PENDING_APPROVAL
    order.payment_rejection_reason = ""
    order.payment_submitted_at = timezone.now()
    order.save(
        update_fields=[
            "payment_status",
            "payment_rejection_reason",
            "payment_submitted_at",
        ]
    )
    log_supply_event(
        company=order.company,
        project=order.project,
        supply_order=order,
        action=(
            SupplyWorkflowLog.ACTION_PAYMENT_RESUBMITTED
            if is_resubmit
            else SupplyWorkflowLog.ACTION_PAYMENT_SUBMITTED
        ),
        user=user,
        comment=f"Сумма: {order.purchase_amount} ₸, поставщик: {order.supplier}",
    )
    return order


@transaction.atomic
def approve_order_payment(order: SupplyOrder, *, user) -> SupplyOrder:
    if order.payment_status != SupplyOrder.PAYMENT_PENDING_APPROVAL:
        raise ValueError("invalid_status")

    order.payment_status = SupplyOrder.PAYMENT_AWAITING
    order.payment_approved_at = timezone.now()
    order.payment_approved_by = user
    order.payment_rejection_reason = ""
    order.save(
        update_fields=[
            "payment_status",
            "payment_approved_at",
            "payment_approved_by",
            "payment_rejection_reason",
        ]
    )
    log_supply_event(
        company=order.company,
        project=order.project,
        supply_order=order,
        action=SupplyWorkflowLog.ACTION_PAYMENT_APPROVED,
        user=user,
        comment="Согласовано к оплате",
    )
    log_supply_event(
        company=order.company,
        project=order.project,
        supply_order=order,
        action=SupplyWorkflowLog.ACTION_TRANSFERRED_TO_FINANCE,
        user=user,
        comment="Ожидает оплаты в разделе «Финансы»",
    )
    mark_order_fully_purchased(order)
    return order


@transaction.atomic
def reject_order_payment(order: SupplyOrder, *, user, reason: str) -> SupplyOrder:
    reason = (reason or "").strip()
    if not reason:
        raise ValueError("reason_required")
    if order.payment_status != SupplyOrder.PAYMENT_PENDING_APPROVAL:
        raise ValueError("invalid_status")

    order.payment_status = SupplyOrder.PAYMENT_REJECTED
    order.payment_rejection_reason = reason[:2000]
    order.save(update_fields=["payment_status", "payment_rejection_reason"])
    log_supply_event(
        company=order.company,
        project=order.project,
        supply_order=order,
        action=SupplyWorkflowLog.ACTION_PAYMENT_REJECTED,
        user=user,
        comment=reason,
    )
    return order


def list_pending_payment_approval(project):
    return (
        SupplyOrder.objects.filter(
            project=project,
            payment_status=SupplyOrder.PAYMENT_PENDING_APPROVAL,
        )
        .select_related("off_estimate_request", "payment_approved_by")
        .prefetch_related(
            "items__request__resource",
            "items__off_estimate_item",
            Prefetch(
                "documents",
                queryset=SupplyOrderDocument.objects.select_related(
                    "uploaded_by"
                ).order_by("doc_type", "-version"),
            ),
        )
        .order_by("-payment_submitted_at", "-created_at")
    )


def enrich_order_documents(order: SupplyOrder) -> dict:
    return {
        "kp_current": get_current_document(order, SupplyOrderDocument.DOC_KP),
        "invoice_current": get_current_document(
            order, SupplyOrderDocument.DOC_INVOICE
        ),
        "kp_history": list(
            get_document_history(order, SupplyOrderDocument.DOC_KP)[:10]
        ),
        "invoice_history": list(
            get_document_history(order, SupplyOrderDocument.DOC_INVOICE)[:10]
        ),
    }
