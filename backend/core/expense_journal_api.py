"""API журнала расходов (автосохранение без перезагрузки)."""
from __future__ import annotations

import json
from datetime import date
from typing import Any

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_GET, require_http_methods

from .access_utils import get_current_company, has_permission
from . import expense_journal_services as ej
from .models import ExpenseJournalEntry, Project
from .rbac import permission_required


def _company(request: HttpRequest):
    company = get_current_company(request.user)
    if not company:
        return None, JsonResponse({"ok": False, "error": "no_company"}, status=403)
    if not has_permission(request.user, company, "view_finance"):
        return None, JsonResponse({"ok": False, "error": "forbidden"}, status=403)
    return company, None


def _parse_filters(request: HttpRequest) -> dict[str, Any]:
    date_from = parse_date(request.GET.get("date_from", "").strip() or "")
    date_to = parse_date(request.GET.get("date_to", "").strip() or "")
    project_id = request.GET.get("project", "").strip()
    responsible_id = request.GET.get("responsible", "").strip()
    payment_method = request.GET.get("payment_method", "").strip()
    return {
        "date_from": date_from,
        "date_to": date_to,
        "project_id": int(project_id) if project_id.isdigit() else None,
        "responsible_id": int(responsible_id) if responsible_id.isdigit() else None,
        "payment_method": payment_method,
    }


@login_required
@require_GET
@permission_required("view_finance")
def api_expense_journal_list(request: HttpRequest) -> HttpResponse:
    company, err = _company(request)
    if err:
        return err
    flt = _parse_filters(request)
    qs = ej.filter_entries(company, **flt)
    kpis = ej.compute_kpis(company, project_id=flt["project_id"])
    return JsonResponse(
        {
            "ok": True,
            "entries": [ej.serialize_entry(r) for r in qs[:2000]],
            "kpis": {k: str(v) for k, v in kpis.items()},
            "employees": ej.list_employees(company),
            "payment_methods": ej.PAYMENT_METHOD_META,
            "projects": [
                {"id": p.pk, "name": p.name}
                for p in Project.objects.filter(company=company).order_by("name")
            ],
            "can_edit": has_permission(request.user, company, "edit_finance"),
        }
    )


@login_required
@require_http_methods(["POST"])
@permission_required("edit_finance")
def api_expense_journal_create(request: HttpRequest) -> HttpResponse:
    company, err = _company(request)
    if err:
        return err
    try:
        data = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "json"}, status=400)
    entry_date = parse_date(str(data.get("date") or "")) or date.today()
    amount = data.get("amount")
    try:
        row = ej.create_entry(
            company,
            user=request.user,
            entry_date=entry_date,
            amount=ej._parse_decimal(amount) if amount not in (None, "") else None,
            purpose=str(data.get("purpose") or ""),
            responsible_id=data.get("responsible_id") or None,
            payment_method=str(data.get("payment_method") or ""),
            project_id=data.get("project_id") or None,
            comment=str(data.get("comment") or ""),
        )
    except ValueError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)
    row = ExpenseJournalEntry.objects.select_related(
        "responsible", "project"
    ).get(pk=row.pk)
    return JsonResponse({"ok": True, "entry": ej.serialize_entry(row)})


@login_required
@require_http_methods(["PATCH", "POST"])
@permission_required("edit_finance")
def api_expense_journal_update(
    request: HttpRequest, entry_id: int
) -> HttpResponse:
    company, err = _company(request)
    if err:
        return err
    row = get_object_or_404(ExpenseJournalEntry, pk=entry_id, company=company)
    try:
        data = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "json"}, status=400)
    payload: dict[str, Any] = {}
    if "date" in data:
        d = parse_date(str(data["date"] or ""))
        if not d:
            return JsonResponse({"ok": False, "error": "bad_date"}, status=400)
        payload["date"] = d
    for key in (
        "amount",
        "purpose",
        "responsible_id",
        "payment_method",
        "project_id",
        "category",
    ):
        if key in data:
            payload[key] = data[key]
    try:
        ej.update_entry(row, data=payload)
    except ValueError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)
    row.refresh_from_db()
    row = ExpenseJournalEntry.objects.select_related(
        "responsible", "project"
    ).get(pk=row.pk)
    return JsonResponse({"ok": True, "entry": ej.serialize_entry(row)})


@login_required
@require_GET
@permission_required("view_finance")
def api_expense_journal_receipt_preview(
    request: HttpRequest, entry_id: int
) -> HttpResponse:
    company, err = _company(request)
    if err:
        return err
    row = get_object_or_404(ExpenseJournalEntry, pk=entry_id, company=company)
    try:
        png = ej.render_receipt_preview_png(row)
    except ValueError:
        return JsonResponse({"ok": False, "error": "no_file"}, status=404)
    resp = HttpResponse(png, content_type="image/png")
    resp["Cache-Control"] = "private, max-age=300"
    return resp


@login_required
@require_http_methods(["POST"])
@permission_required("edit_finance")
def api_expense_journal_upload_receipt(
    request: HttpRequest, entry_id: int
) -> HttpResponse:
    company, err = _company(request)
    if err:
        return err
    row = get_object_or_404(ExpenseJournalEntry, pk=entry_id, company=company)
    uploaded = request.FILES.get("file") or request.FILES.get("receipt_pdf")
    try:
        ej.upload_receipt_pdf(row, uploaded)
    except ValueError as exc:
        code = str(exc)
        if code == "no_file":
            return JsonResponse({"ok": False, "error": "no_file"}, status=400)
        if code == "bad_extension":
            return JsonResponse({"ok": False, "error": "bad_extension"}, status=400)
        return JsonResponse({"ok": False, "error": code}, status=400)
    row = ExpenseJournalEntry.objects.select_related(
        "responsible", "project"
    ).get(pk=row.pk)
    return JsonResponse({"ok": True, "entry": ej.serialize_entry(row)})


@login_required
@require_http_methods(["DELETE", "POST"])
@permission_required("edit_finance")
def api_expense_journal_delete(
    request: HttpRequest, entry_id: int
) -> HttpResponse:
    company, err = _company(request)
    if err:
        return err
    row = get_object_or_404(ExpenseJournalEntry, pk=entry_id, company=company)
    ej.delete_entry(row)
    return JsonResponse({"ok": True})


@login_required
@require_GET
@permission_required("view_finance")
def api_expense_journal_export_xlsx(request: HttpRequest) -> HttpResponse:
    company, err = _company(request)
    if err:
        return err
    flt = _parse_filters(request)
    qs = ej.filter_entries(company, **flt)
    buf = ej.export_xlsx(company, qs)
    resp = HttpResponse(
        buf.read(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    resp["Content-Disposition"] = 'attachment; filename="expense_journal.xlsx"'
    return resp


@login_required
@require_GET
@permission_required("view_finance")
def api_expense_journal_export_pdf(request: HttpRequest) -> HttpResponse:
    company, err = _company(request)
    if err:
        return err
    flt = _parse_filters(request)
    qs = ej.filter_entries(company, **flt)
    buf = ej.export_pdf(company, qs)
    resp = HttpResponse(buf.read(), content_type="application/pdf")
    resp["Content-Disposition"] = 'attachment; filename="expense_journal.pdf"'
    return resp
