"""Views/API workflow снабжения."""
from __future__ import annotations

import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from .access_utils import get_current_company, has_permission
from .models import (
    OffEstimateSupplyRequest,
    SupplyOrder,
    SupplyOrderItem,
    SupplyRequest,
    Warehouse,
)
from . import supply_workflow_services as wf
from . import supply_payment_services as pay
from .rbac import permission_required


def _project(request, pk):
    company = get_current_company(request.user)
    if not company:
        return None, redirect("/")
    from .models import Project

    project = get_object_or_404(Project, pk=pk, company=company)
    return project, None


def _can_approve(user, company) -> bool:
    return has_permission(user, company, "approve_supply_request")


def _can_procure(user, company) -> bool:
    return has_permission(user, company, "procure_supply") or has_permission(
        user, company, "edit_supply"
    )


def _can_receive(user, company) -> bool:
    return has_permission(user, company, "receive_supply_warehouse") or has_permission(
        user, company, "edit_warehouse"
    )


@login_required
@require_POST
@permission_required("approve_supply_request")
def project_supply_approve_estimate(
    request: HttpRequest, pk: int, req_id: int
) -> HttpResponse:
    project, err = _project(request, pk)
    if err:
        return err
    sr = get_object_or_404(
        SupplyRequest, pk=req_id, project=project, company=project.company
    )
    supplier = (request.POST.get("supplier") or "").strip()
    try:
        wf.approve_supply_request(supply_request=sr, user=request.user, supplier=supplier)
    except ValueError as e:
        messages.error(request, f"Не удалось согласовать: {e}")
    else:
        messages.success(request, "Заявка согласована. Создан заказ в разделе «Заказы».")
    return redirect(f"{reverse('project_supply', args=[project.pk])}?tab=approval")


@login_required
@require_POST
@permission_required("approve_supply_request")
def project_supply_reject_estimate(
    request: HttpRequest, pk: int, req_id: int
) -> HttpResponse:
    project, err = _project(request, pk)
    if err:
        return err
    sr = get_object_or_404(
        SupplyRequest, pk=req_id, project=project, company=project.company
    )
    reason = (request.POST.get("rejection_reason") or "").strip()
    try:
        wf.reject_supply_request(
            supply_request=sr, user=request.user, reason=reason
        )
    except ValueError as e:
        if str(e) == "reason_required":
            messages.error(request, "Укажите причину отказа.")
        else:
            messages.error(request, f"Не удалось отклонить: {e}")
    else:
        messages.success(request, "Заявка отклонена.")
    return redirect(f"{reverse('project_supply', args=[project.pk])}?tab=approval")


@login_required
@require_POST
@permission_required("approve_supply_request")
def project_supply_approve_off_estimate(
    request: HttpRequest, pk: int, req_id: int
) -> HttpResponse:
    project, err = _project(request, pk)
    if err:
        return err
    oer = get_object_or_404(
        OffEstimateSupplyRequest,
        pk=req_id,
        project=project,
        company=project.company,
    )
    supplier = (request.POST.get("supplier") or "").strip()
    try:
        wf.approve_supply_request(
            off_estimate_request=oer, user=request.user, supplier=supplier
        )
    except ValueError as e:
        messages.error(request, f"Не удалось согласовать: {e}")
    else:
        messages.success(request, f"Заявка {oer.number} согласована. Создан заказ.")
    return redirect(f"{reverse('project_supply', args=[project.pk])}?tab=approval")


@login_required
@require_POST
@permission_required("approve_supply_request")
def project_supply_reject_off_estimate(
    request: HttpRequest, pk: int, req_id: int
) -> HttpResponse:
    project, err = _project(request, pk)
    if err:
        return err
    oer = get_object_or_404(
        OffEstimateSupplyRequest,
        pk=req_id,
        project=project,
        company=project.company,
    )
    reason = (request.POST.get("rejection_reason") or "").strip()
    try:
        wf.reject_supply_request(
            off_estimate_request=oer, user=request.user, reason=reason
        )
    except ValueError as e:
        if str(e) == "reason_required":
            messages.error(request, "Укажите причину отказа.")
        else:
            messages.error(request, f"Не удалось отклонить: {e}")
    else:
        messages.success(request, f"Заявка {oer.number} отклонена.")
    return redirect(f"{reverse('project_supply', args=[project.pk])}?tab=approval")


@login_required
@require_POST
@permission_required("procure_supply")
def project_supply_order_start(
    request: HttpRequest, pk: int, order_id: int
) -> HttpResponse:
    project, err = _project(request, pk)
    if err:
        return err
    order = get_object_or_404(
        SupplyOrder, pk=order_id, project=project, company=project.company
    )
    supplier = (request.POST.get("supplier") or order.supplier or "").strip()
    try:
        wf.start_order_procurement(order, user=request.user, supplier=supplier)
    except ValueError:
        messages.error(request, "Нельзя начать закупку для этого заказа.")
    else:
        messages.success(request, "Закупка начата.")
    return redirect(f"{reverse('project_supply', args=[project.pk])}?tab=orders")


@login_required
@require_POST
@permission_required("procure_supply")
def project_supply_order_purchase(
    request: HttpRequest, pk: int, order_id: int
) -> HttpResponse:
    project, err = _project(request, pk)
    if err:
        return err
    order = get_object_or_404(
        SupplyOrder, pk=order_id, project=project, company=project.company
    )
    updated = 0
    for item in order.items.all():
        key = f"item_{item.pk}"
        if key not in request.POST:
            continue
        try:
            qty = wf.parse_purchased_qty(request.POST.get(key))
            wf.update_order_item_purchased(
                item, quantity_purchased=qty, user=request.user
            )
            updated += 1
        except ValueError:
            messages.error(request, f"Некорректное количество для «{item.display_name}».")
            return redirect(
                f"{reverse('project_supply', args=[project.pk])}?tab=orders"
            )
    if updated:
        messages.success(request, "Данные закупки сохранены.")
    return redirect(f"{reverse('project_supply', args=[project.pk])}?tab=orders")


@login_required
@require_POST
@permission_required("receive_supply_warehouse")
def project_supply_order_warehouse(
    request: HttpRequest, pk: int, order_id: int
) -> HttpResponse:
    project, err = _project(request, pk)
    if err:
        return err
    order = get_object_or_404(
        SupplyOrder, pk=order_id, project=project, company=project.company
    )
    wh_id = request.POST.get("warehouse_id")
    warehouse = get_object_or_404(
        Warehouse, pk=wh_id, company=project.company, is_deleted=False
    )
    try:
        wf.transfer_order_to_warehouse(order, warehouse=warehouse, user=request.user)
    except ValueError as e:
        messages.error(request, f"Не удалось передать на склад: {e}")
    else:
        messages.success(request, f"Материалы оприходованы на склад «{warehouse.name}».")
    return redirect(f"{reverse('project_supply', args=[project.pk])}?tab=orders")


@login_required
@require_POST
@permission_required("procure_supply")
def project_supply_order_cancel(
    request: HttpRequest, pk: int, order_id: int
) -> HttpResponse:
    project, err = _project(request, pk)
    if err:
        return err
    order = get_object_or_404(
        SupplyOrder, pk=order_id, project=project, company=project.company
    )
    reason = (request.POST.get("reason") or "").strip()
    try:
        wf.cancel_order(order, user=request.user, reason=reason)
    except ValueError:
        messages.error(request, "Заказ уже полностью закуплен — отмена невозможна.")
    else:
        messages.success(request, "Заказ отменён.")
    return redirect(f"{reverse('project_supply', args=[project.pk])}?tab=orders")


def _can_approve_payment(user, company) -> bool:
    return has_permission(user, company, "approve_procurement_payment")


_PAYMENT_ERROR_MSG = {
    "not_editable": "Редактирование недоступно в текущем статусе оплаты.",
    "cancelled": "Заказ отменён.",
    "invalid_status": "Недопустимый статус для этого действия.",
    "supplier_required": "Укажите поставщика.",
    "amount_required": "Укажите сумму закупки.",
    "document_required": "Загрузите коммерческое предложение и/или счёт на оплату.",
    "reason_required": "Укажите причину отказа.",
    "no_file": "Файл не выбран.",
    "bad_extension": "Допустимые форматы: pdf, doc, docx, xls, xlsx, jpg, png.",
    "bad_amount": "Некорректная сумма.",
}


def _payment_error_message(exc: ValueError) -> str:
    return _PAYMENT_ERROR_MSG.get(str(exc), str(exc))


@login_required
@require_POST
@permission_required("procure_supply")
def project_supply_order_update_payment_info(
    request: HttpRequest, pk: int, order_id: int
) -> HttpResponse:
    project, err = _project(request, pk)
    if err:
        return err
    order = get_object_or_404(SupplyOrder, pk=order_id, project=project)
    from django.utils.dateparse import parse_date

    planned = None
    raw_date = request.POST.get("planned_delivery_date", "").strip()
    if raw_date:
        planned = parse_date(raw_date)
    try:
        pay.update_order_procurement_info(
            order,
            user=request.user,
            supplier=request.POST.get("supplier", ""),
            purchase_amount_raw=request.POST.get("purchase_amount"),
            planned_delivery_date=planned,
            procurement_note=request.POST.get("procurement_note", ""),
        )
    except ValueError as exc:
        messages.error(request, _payment_error_message(exc))
    else:
        messages.success(request, "Данные заказа сохранены.")
    return redirect(f"{reverse('project_supply', args=[project.pk])}?tab=orders")


@login_required
@require_POST
@permission_required("procure_supply")
def project_supply_order_upload_document(
    request: HttpRequest, pk: int, order_id: int
) -> HttpResponse:
    project, err = _project(request, pk)
    if err:
        return err
    order = get_object_or_404(SupplyOrder, pk=order_id, project=project)
    doc_type = request.POST.get("doc_type", "")
    uploaded = request.FILES.get("file")
    try:
        pay.upload_order_document(
            order, user=request.user, doc_type=doc_type, uploaded_file=uploaded
        )
    except ValueError as exc:
        messages.error(request, _payment_error_message(exc))
    else:
        messages.success(request, "Документ загружен.")
    return redirect(f"{reverse('project_supply', args=[project.pk])}?tab=orders")


@login_required
@require_POST
@permission_required("procure_supply")
def project_supply_order_submit_payment_approval(
    request: HttpRequest, pk: int, order_id: int
) -> HttpResponse:
    project, err = _project(request, pk)
    if err:
        return err
    order = get_object_or_404(SupplyOrder, pk=order_id, project=project)
    try:
        pay.submit_order_for_payment_approval(order, user=request.user)
    except ValueError as exc:
        messages.error(request, _payment_error_message(exc))
    else:
        messages.success(
            request, "Заказ отправлен на согласование оплаты.",
        )
    return redirect(f"{reverse('project_supply', args=[project.pk])}?tab=orders")


@login_required
@require_POST
@permission_required("approve_procurement_payment")
def project_supply_order_approve_payment(
    request: HttpRequest, pk: int, order_id: int
) -> HttpResponse:
    project, err = _project(request, pk)
    if err:
        return err
    order = get_object_or_404(SupplyOrder, pk=order_id, project=project)
    try:
        pay.approve_order_payment(order, user=request.user)
    except ValueError as exc:
        messages.error(request, _payment_error_message(exc))
    else:
        messages.success(
            request,
            "Оплата согласована. Заказ передан в «Финансы → Заказы на оплату».",
        )
    return redirect(
        f"{reverse('project_supply', args=[project.pk])}?tab=procurement_approval"
    )


@login_required
@require_POST
@permission_required("approve_procurement_payment")
def project_supply_order_reject_payment(
    request: HttpRequest, pk: int, order_id: int
) -> HttpResponse:
    project, err = _project(request, pk)
    if err:
        return err
    order = get_object_or_404(SupplyOrder, pk=order_id, project=project)
    reason = request.POST.get("rejection_reason", "")
    try:
        pay.reject_order_payment(order, user=request.user, reason=reason)
    except ValueError as exc:
        messages.error(request, _payment_error_message(exc))
    else:
        messages.success(request, "Оплата отклонена. Снабженец может исправить данные и отправить снова.")
    return redirect(
        f"{reverse('project_supply', args=[project.pk])}?tab=procurement_approval"
    )


@login_required
@require_GET
@permission_required("view_supply")
def project_supply_workflow_history(
    request: HttpRequest, pk: int
) -> JsonResponse:
    project, err = _project(request, pk)
    if err:
        return JsonResponse({"ok": False, "error": "forbidden"}, status=403)
    req_type = request.GET.get("type", "")
    req_id = request.GET.get("id", "")
    logs = []
    if req_type == "estimate" and req_id.isdigit():
        sr = get_object_or_404(
            SupplyRequest, pk=int(req_id), project=project
        )
        logs = wf.get_workflow_logs_for_request(supply_request=sr)
    elif req_type == "off_estimate" and req_id.isdigit():
        oer = get_object_or_404(
            OffEstimateSupplyRequest, pk=int(req_id), project=project
        )
        logs = wf.get_workflow_logs_for_request(off_estimate_request=oer)
    elif req_type == "order" and req_id.isdigit():
        order = get_object_or_404(SupplyOrder, pk=int(req_id), project=project)
        logs = wf.get_workflow_logs_for_order(order)
    else:
        return JsonResponse({"ok": False, "error": "bad_params"}, status=400)

    rows = [
        {
            "at": log.created_at.strftime("%d.%m.%Y %H:%M"),
            "action": log.get_action_display(),
            "user": log.user.get_username() if log.user else "—",
            "comment": log.comment or "",
        }
        for log in logs
    ]
    return JsonResponse({"ok": True, "events": rows})
