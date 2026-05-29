"""JSON API табеля работников в контексте проекта."""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.http import require_GET, require_http_methods

from . import timesheet_services as ts
from .access_utils import has_permission
from .models import Employee, ProjectEmployee, TimesheetEntryLog
from .rbac import permission_required


def _json(body: dict[str, Any], status: int = 200) -> JsonResponse:
    return JsonResponse(body, status=status, json_dumps_params={"ensure_ascii": False})


def _can_edit(user, company) -> bool:
    return has_permission(user, company, "edit_timesheet")


def _project(request: HttpRequest, pk: int):
    from .views import _get_project_or_403

    return _get_project_or_403(request, pk)


def _parse_year_month(request: HttpRequest) -> tuple[int, int] | None:
    try:
        year = int(request.GET.get("year") or date.today().year)
        month = int(request.GET.get("month") or date.today().month)
    except (TypeError, ValueError):
        return None
    if month < 1 or month > 12 or year < 2000 or year > 2100:
        return None
    return year, month


@require_GET
@permission_required("view_timesheet")
def api_project_timesheet_month(request: HttpRequest, pk: int) -> HttpResponse:
    project, err = _project(request, pk)
    if err:
        return err
    ym = _parse_year_month(request)
    if not ym:
        return _json({"ok": False, "error": "year/month"}, status=400)
    year, month = ym

    employees = [
        ts.serialize_employee(pe)
        for pe in ts.project_employees_qs(project)
    ]
    _, _, days = ts.month_bounds(year, month)
    entries = ts.entries_map_for_month(project, year, month)
    analytics = ts.compute_analytics(project, year, month)

    return _json(
        {
            "ok": True,
            "can_edit": _can_edit(request.user, project.company),
            "year": year,
            "month": month,
            "days_in_month": days,
            "employees": employees,
            "entries": entries,
            "statuses": ts.STATUS_META,
            "analytics": analytics,
            "today": date.today().isoformat(),
        }
    )


@require_http_methods(["POST"])
@permission_required("edit_timesheet")
def api_project_timesheet_cell(request: HttpRequest, pk: int) -> HttpResponse:
    project, err = _project(request, pk)
    if err:
        return err
    try:
        data = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return _json({"ok": False, "error": "json"}, status=400)

    try:
        employee_id = int(data.get("employee_id"))
        day = datetime.strptime(str(data["date"])[:10], "%Y-%m-%d").date()
        status = str(data.get("status") or "").strip()
        comment = str(data.get("comment") or "")
    except (TypeError, ValueError, KeyError):
        return _json({"ok": False, "error": "fields"}, status=400)

    try:
        ent = ts.upsert_cell(
            project=project,
            employee_id=employee_id,
            day=day,
            status=status,
            comment=comment,
            user=request.user,
        )
    except ValueError as e:
        return _json({"ok": False, "error": str(e)}, status=400)

    return _json(
        {
            "ok": True,
            "entry": {
                "employee_id": employee_id,
                "date": day.isoformat(),
                "status": ent.status if ent else "",
            },
        }
    )


@require_http_methods(["POST"])
@permission_required("edit_timesheet")
def api_project_timesheet_bulk(request: HttpRequest, pk: int) -> HttpResponse:
    project, err = _project(request, pk)
    if err:
        return err
    try:
        data = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return _json({"ok": False, "error": "json"}, status=400)

    updates = data.get("updates") or data.get("cells") or []
    if not isinstance(updates, list):
        return _json({"ok": False, "error": "updates"}, status=400)

    count = ts.bulk_upsert_cells(
        project=project,
        updates=updates,
        user=request.user,
    )
    return _json({"ok": True, "updated": count})


@require_GET
@permission_required("view_timesheet")
def api_project_timesheet_export(request: HttpRequest, pk: int) -> HttpResponse:
    project, err = _project(request, pk)
    if err:
        return err
    ym = _parse_year_month(request)
    if not ym:
        return _json({"ok": False, "error": "year/month"}, status=400)
    year, month = ym
    buf = ts.export_timesheet_xlsx(project, year, month)
    resp = HttpResponse(
        buf.read(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    resp["Content-Disposition"] = (
        f'attachment; filename="timesheet_{project.pk}_{year}_{month:02d}.xlsx"'
    )
    return resp


@require_http_methods(["POST"])
@permission_required("edit_timesheet")
def api_project_timesheet_import_employees(
    request: HttpRequest, pk: int
) -> HttpResponse:
    project, err = _project(request, pk)
    if err:
        return err
    f = request.FILES.get("file")
    if not f:
        return _json({"ok": False, "error": "file"}, status=400)
    try:
        stats = ts.import_employees_from_xlsx(project, f)
    except Exception as e:
        return _json({"ok": False, "error": str(e)}, status=400)
    return _json({"ok": True, **stats})


@require_GET
@permission_required("view_timesheet")
def api_project_timesheet_logs(request: HttpRequest, pk: int) -> HttpResponse:
    project, err = _project(request, pk)
    if err:
        return err
    limit = min(200, max(1, int(request.GET.get("limit") or 50)))
    logs = (
        TimesheetEntryLog.objects.filter(project=project)
        .select_related("employee", "edited_by")
        .order_by("-edited_at")[:limit]
    )
    items = []
    for lg in logs:
        items.append(
            {
                "id": lg.pk,
                "employee_name": lg.employee.full_name,
                "date": lg.date.isoformat(),
                "old_status": lg.old_status,
                "new_status": lg.new_status,
                "old_short": ts.STATUS_SHORT_BY_CODE.get(lg.old_status, ""),
                "new_short": ts.STATUS_SHORT_BY_CODE.get(lg.new_status, ""),
                "edited_by": lg.edited_by.get_username() if lg.edited_by else "",
                "edited_at": lg.edited_at.isoformat(),
            }
        )
    return _json({"ok": True, "logs": items})


@require_http_methods(["POST"])
@permission_required("edit_timesheet")
def api_project_timesheet_employee_create(
    request: HttpRequest, pk: int
) -> HttpResponse:
    project, err = _project(request, pk)
    if err:
        return err
    try:
        data = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return _json({"ok": False, "error": "json"}, status=400)

    try:
        pe = ts.create_project_employee(
            project,
            full_name=str(data.get("full_name") or ""),
            position=str(data.get("position") or ""),
            phone=str(data.get("phone") or ""),
            brigade=str(data.get("brigade") or ""),
            status=str(data.get("status") or Employee.STATUS_ACTIVE),
        )
    except ValueError as e:
        code = str(e)
        status = 400
        if code == "duplicate_name":
            status = 409
        return _json({"ok": False, "error": code}, status=status)

    return _json({"ok": True, "employee": ts.serialize_employee(pe)})


@require_http_methods(["POST", "PATCH"])
@permission_required("edit_timesheet")
def api_project_timesheet_employee_update(
    request: HttpRequest, pk: int, employee_id: int
) -> HttpResponse:
    project, err = _project(request, pk)
    if err:
        return err
    try:
        data = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return _json({"ok": False, "error": "json"}, status=400)

    try:
        pe = ts.update_project_employee(
            project,
            employee_id,
            full_name=data.get("full_name"),
            position=data.get("position"),
            phone=data.get("phone"),
            brigade=data.get("brigade"),
            status=data.get("status"),
        )
    except ValueError as e:
        code = str(e)
        status = 404 if code == "employee" else 400
        if code == "duplicate_name":
            status = 409
        return _json({"ok": False, "error": code}, status=status)

    return _json({"ok": True, "employee": ts.serialize_employee(pe)})


@require_http_methods(["POST", "DELETE"])
@permission_required("edit_timesheet")
def api_project_timesheet_employee_remove(
    request: HttpRequest, pk: int, employee_id: int
) -> HttpResponse:
    project, err = _project(request, pk)
    if err:
        return err
    try:
        ts.remove_project_employee(project, employee_id)
    except ValueError:
        return _json({"ok": False, "error": "employee"}, status=404)
    return _json({"ok": True})
