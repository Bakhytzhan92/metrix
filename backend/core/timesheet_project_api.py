"""Устаревший API табеля в контексте проекта — делегирует в company API."""

from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.views.decorators.http import require_GET, require_http_methods

from . import timesheet_api
from .rbac import permission_required


def _project_company_api(request: HttpRequest, pk: int):
    from .views import _get_project_or_403

    project, err = _get_project_or_403(request, pk)
    if err:
        return None, err
    return project.company, None


@require_GET
@permission_required("view_timesheet")
def api_project_timesheet_month(request: HttpRequest, pk: int) -> HttpResponse:
    _, err = _project_company_api(request, pk)
    if err:
        return err
    return timesheet_api.api_timesheet_month(request)


@require_http_methods(["POST"])
@permission_required("edit_timesheet")
def api_project_timesheet_cell(request: HttpRequest, pk: int) -> HttpResponse:
    _, err = _project_company_api(request, pk)
    if err:
        return err
    return timesheet_api.api_timesheet_cell(request)


@require_http_methods(["POST"])
@permission_required("edit_timesheet")
def api_project_timesheet_bulk(request: HttpRequest, pk: int) -> HttpResponse:
    _, err = _project_company_api(request, pk)
    if err:
        return err
    return timesheet_api.api_timesheet_bulk(request)


@require_GET
@permission_required("view_timesheet")
def api_project_timesheet_export(request: HttpRequest, pk: int) -> HttpResponse:
    _, err = _project_company_api(request, pk)
    if err:
        return err
    return timesheet_api.api_timesheet_export(request)


@require_http_methods(["POST"])
@permission_required("edit_timesheet")
def api_project_timesheet_import_employees(
    request: HttpRequest, pk: int
) -> HttpResponse:
    _, err = _project_company_api(request, pk)
    if err:
        return err
    return timesheet_api.api_timesheet_import_employees(request)


@require_GET
@permission_required("view_timesheet")
def api_project_timesheet_logs(request: HttpRequest, pk: int) -> HttpResponse:
    _, err = _project_company_api(request, pk)
    if err:
        return err
    return timesheet_api.api_timesheet_logs(request)


@require_http_methods(["POST"])
@permission_required("edit_timesheet")
def api_project_timesheet_employee_create(
    request: HttpRequest, pk: int
) -> HttpResponse:
    _, err = _project_company_api(request, pk)
    if err:
        return err
    return timesheet_api.api_timesheet_employee_create(request)


@require_http_methods(["POST", "PATCH"])
@permission_required("edit_timesheet")
def api_project_timesheet_employee_update(
    request: HttpRequest, pk: int, employee_id: int
) -> HttpResponse:
    _, err = _project_company_api(request, pk)
    if err:
        return err
    return timesheet_api.api_timesheet_employee_update(request, employee_id)


@require_http_methods(["POST", "DELETE"])
@permission_required("edit_timesheet")
def api_project_timesheet_employee_remove(
    request: HttpRequest, pk: int, employee_id: int
) -> HttpResponse:
    _, err = _project_company_api(request, pk)
    if err:
        return err
    return timesheet_api.api_timesheet_employee_remove(request, employee_id)
