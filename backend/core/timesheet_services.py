"""Табель работников: бизнес-логика, Excel, аналитика."""

from __future__ import annotations

import calendar
from datetime import date, datetime
from io import BytesIO
from typing import Any

from django.contrib.auth import get_user_model
from django.db import transaction
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill

from .models import (
    Employee,
    Project,
    ProjectEmployee,
    Timesheet,
    TimesheetEntry,
    TimesheetEntryLog,
)

User = get_user_model()

STATUS_META: list[dict[str, str]] = [
    {"code": TimesheetEntry.STATUS_PRESENT, "short": "Я", "label": "Явка", "color": "#22c55e"},
    {"code": TimesheetEntry.STATUS_OFF, "short": "В", "label": "Выходной", "color": "#94a3b8"},
    {"code": TimesheetEntry.STATUS_VACATION, "short": "О", "label": "Отпуск", "color": "#6366f1"},
    {"code": TimesheetEntry.STATUS_ABSENT, "short": "Н", "label": "Неявка", "color": "#ef4444"},
    {"code": TimesheetEntry.STATUS_HALF, "short": "П", "label": "Полдня", "color": "#f59e0b"},
]

STATUS_SHORT_BY_CODE = {m["code"]: m["short"] for m in STATUS_META}
STATUS_LABEL_BY_CODE = {m["code"]: m["label"] for m in STATUS_META}
VALID_STATUS_CODES = set(STATUS_SHORT_BY_CODE)


def month_bounds(year: int, month: int) -> tuple[date, date, int]:
    days = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, days), days


def get_or_create_timesheet(project: Project, year: int, month: int) -> Timesheet:
    ts, _ = Timesheet.objects.get_or_create(
        project=project,
        year=year,
        month=month,
    )
    return ts


def project_employees_qs(project: Project, *, brigade: str = ""):
    qs = (
        ProjectEmployee.objects.filter(
            project=project,
            is_active=True,
            employee__status=Employee.STATUS_ACTIVE,
        )
        .select_related("employee")
        .order_by("employee__full_name", "employee_id")
    )
    if brigade:
        qs = qs.filter(employee__brigade__iexact=brigade.strip())
    return qs


def serialize_employee(pe: ProjectEmployee) -> dict[str, Any]:
    e = pe.employee
    return {
        "id": e.pk,
        "project_employee_id": pe.pk,
        "full_name": e.full_name,
        "position": e.position or "",
        "status": e.status,
        "status_display": e.get_status_display(),
    }


def entries_map_for_month(
    project: Project, year: int, month: int
) -> dict[str, str]:
    start, end, _ = month_bounds(year, month)
    out: dict[str, str] = {}
    qs = TimesheetEntry.objects.filter(
        project=project,
        date__gte=start,
        date__lte=end,
    ).values_list("employee_id", "date", "status")
    for eid, d, st in qs:
        out[f"{eid}:{d.isoformat()}"] = st or ""
    return out


def compute_analytics(
    project: Project,
    year: int,
    month: int,
    *,
    today: date | None = None,
) -> dict[str, Any]:
    today = today or date.today()
    employees = list(project_employees_qs(project))
    total_workers = len(employees)
    emp_ids = [pe.employee_id for pe in employees]

    on_site_today = 0
    absent_today = 0
    if emp_ids and today.year == year and today.month == month:
        today_entries = TimesheetEntry.objects.filter(
            project=project,
            employee_id__in=emp_ids,
            date=today,
        )
        for ent in today_entries:
            if ent.status in (TimesheetEntry.STATUS_PRESENT, TimesheetEntry.STATUS_HALF):
                on_site_today += 1
            elif ent.status == TimesheetEntry.STATUS_ABSENT:
                absent_today += 1

    start, end, days_in_month = month_bounds(year, month)
    filled = TimesheetEntry.objects.filter(
        project=project,
        date__gte=start,
        date__lte=end,
        employee_id__in=emp_ids,
        status__in=[TimesheetEntry.STATUS_PRESENT, TimesheetEntry.STATUS_HALF],
    ).count()
    possible = max(1, total_workers * days_in_month)
    attendance_pct = round(100.0 * filled / possible, 1)

    return {
        "total_workers": total_workers,
        "on_site_today": on_site_today,
        "absent_today": absent_today,
        "attendance_pct": attendance_pct,
    }


def log_entry_change(
    *,
    project: Project,
    employee: Employee,
    entry: TimesheetEntry | None,
    day: date,
    old_status: str,
    new_status: str,
    user: User | None,
) -> None:
    TimesheetEntryLog.objects.create(
        project=project,
        employee=employee,
        entry=entry,
        date=day,
        old_status=old_status or "",
        new_status=new_status or "",
        edited_by=user,
    )


@transaction.atomic
def upsert_cell(
    *,
    project: Project,
    employee_id: int,
    day: date,
    status: str,
    comment: str = "",
    user: User | None = None,
) -> TimesheetEntry | None:
    if status and status not in VALID_STATUS_CODES:
        raise ValueError("invalid status")
    employee = Employee.objects.filter(
        pk=employee_id,
        company_id=project.company_id,
    ).first()
    if not employee:
        raise ValueError("employee not found")
    if not ProjectEmployee.objects.filter(
        project=project, employee=employee, is_active=True
    ).exists():
        raise ValueError("employee not on project")

    ts = get_or_create_timesheet(project, day.year, day.month)
    ent = TimesheetEntry.objects.filter(
        timesheet=ts, employee=employee, date=day
    ).first()
    old_status = ent.status if ent else ""

    if not status:
        if ent:
            log_entry_change(
                project=project,
                employee=employee,
                entry=ent,
                day=day,
                old_status=old_status,
                new_status="",
                user=user,
            )
            ent.delete()
        return None

    if ent:
        ent.status = status
        ent.comment = comment or ent.comment
        ent.edited_by = user
        ent.save(update_fields=["status", "comment", "edited_by", "edited_at"])
    else:
        ent = TimesheetEntry.objects.create(
            timesheet=ts,
            project=project,
            employee=employee,
            date=day,
            status=status,
            comment=comment or "",
            edited_by=user,
        )

    if old_status != status:
        log_entry_change(
            project=project,
            employee=employee,
            entry=ent,
            day=day,
            old_status=old_status,
            new_status=status,
            user=user,
        )
    return ent


@transaction.atomic
def bulk_upsert_cells(
    *,
    project: Project,
    updates: list[dict[str, Any]],
    user: User | None = None,
) -> int:
    count = 0
    for u in updates:
        eid = u.get("employee_id")
        ds = u.get("date")
        st = u.get("status", "")
        if not eid or not ds:
            continue
        try:
            day = datetime.strptime(str(ds)[:10], "%Y-%m-%d").date()
        except ValueError:
            continue
        upsert_cell(
            project=project,
            employee_id=int(eid),
            day=day,
            status=st or "",
            comment=str(u.get("comment") or ""),
            user=user,
        )
        count += 1
    return count


def export_timesheet_xlsx(
    project: Project, year: int, month: int
) -> BytesIO:
    start, end, days = month_bounds(year, month)
    employees = [pe.employee for pe in project_employees_qs(project)]
    entries = entries_map_for_month(project, year, month)

    wb = Workbook()
    ws = wb.active
    ws.title = f"Табель {month:02d}.{year}"

    title = f"ТАБЕЛЬ учёта рабочего времени — {project.name} — {month:02d}.{year}"
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=days + 2)
    ws["A1"] = title
    ws["A1"].font = Font(bold=True, size=12)

    headers = ["№", "ФИО", "Должность"] + [str(d) for d in range(1, days + 1)]
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=3, column=col, value=h)
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="center", vertical="center")

    fill_map = {
        TimesheetEntry.STATUS_PRESENT: PatternFill("solid", fgColor="DCFCE7"),
        TimesheetEntry.STATUS_OFF: PatternFill("solid", fgColor="F1F5F9"),
        TimesheetEntry.STATUS_VACATION: PatternFill("solid", fgColor="E0E7FF"),
        TimesheetEntry.STATUS_ABSENT: PatternFill("solid", fgColor="FEE2E2"),
        TimesheetEntry.STATUS_HALF: PatternFill("solid", fgColor="FEF3C7"),
    }

    for i, emp in enumerate(employees, 1):
        row = 3 + i
        ws.cell(row=row, column=1, value=i)
        ws.cell(row=row, column=2, value=emp.full_name)
        ws.cell(row=row, column=3, value=emp.position or "")
        for d in range(1, days + 1):
            day = date(year, month, d)
            key = f"{emp.pk}:{day.isoformat()}"
            st = entries.get(key, "")
            col = 3 + d
            cell = ws.cell(
                row=row,
                column=col,
                value=STATUS_SHORT_BY_CODE.get(st, ""),
            )
            cell.alignment = Alignment(horizontal="center")
            if st in fill_map:
                cell.fill = fill_map[st]

    legend_row = 3 + len(employees) + 2
    ws.cell(row=legend_row, column=1, value="Условные обозначения:")
    for j, m in enumerate(STATUS_META):
        ws.cell(
            row=legend_row,
            column=2 + j,
            value=f"{m['short']} — {m['label']}",
        )

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


@transaction.atomic
def import_employees_from_xlsx(project: Project, file_obj) -> dict[str, int]:
    wb = load_workbook(file_obj, read_only=True, data_only=True)
    ws = wb.active
    created = 0
    linked = 0
    updated = 0
    company = project.company

    rows = list(ws.iter_rows(min_row=2, values_only=True))
    for row in rows:
        if not row:
            continue
        full_name = str(row[0] or "").strip()
        if not full_name or full_name.lower() in ("фio", "фio", "фио", "fio"):
            continue
        position = str(row[1] or "").strip() if len(row) > 1 else ""

        emp = Employee.objects.filter(
            company=company, full_name__iexact=full_name
        ).first()
        if emp:
            changed = False
            if position and emp.position != position:
                emp.position = position
                changed = True
            if emp.status != Employee.STATUS_ACTIVE:
                emp.status = Employee.STATUS_ACTIVE
                changed = True
            if changed:
                emp.save()
                updated += 1
        else:
            emp = Employee.objects.create(
                company=company,
                full_name=full_name,
                position=position,
                status=Employee.STATUS_ACTIVE,
            )
            created += 1

        _, was_created = ProjectEmployee.objects.get_or_create(
            project=project,
            employee=emp,
            defaults={"is_active": True},
        )
        if was_created:
            linked += 1
        elif not ProjectEmployee.objects.filter(
            project=project, employee=emp, is_active=True
        ).exists():
            ProjectEmployee.objects.filter(
                project=project, employee=emp
            ).update(is_active=True)
            linked += 1

    return {"created": created, "linked": linked, "updated": updated}


def _normalize_employee_status(status: str) -> str:
    s = (status or "").strip()
    if s in (Employee.STATUS_ACTIVE, Employee.STATUS_INACTIVE):
        return s
    return Employee.STATUS_ACTIVE


@transaction.atomic
def create_project_employee(
    project: Project,
    *,
    full_name: str,
    position: str = "",
    phone: str = "",
    brigade: str = "",
    status: str = Employee.STATUS_ACTIVE,
) -> ProjectEmployee:
    full_name = (full_name or "").strip()
    if not full_name:
        raise ValueError("full_name")

    company = project.company
    emp = Employee.objects.filter(
        company=company, full_name__iexact=full_name
    ).first()
    if emp:
        emp.position = (position or "").strip()
        emp.phone = (phone or "").strip()
        emp.brigade = (brigade or "").strip()
        emp.status = _normalize_employee_status(status)
        emp.save()
    else:
        emp = Employee.objects.create(
            company=company,
            full_name=full_name,
            position=(position or "").strip(),
            phone=(phone or "").strip(),
            brigade=(brigade or "").strip(),
            status=_normalize_employee_status(status),
        )

    pe, _ = ProjectEmployee.objects.get_or_create(
        project=project,
        employee=emp,
        defaults={"is_active": True},
    )
    if not pe.is_active:
        pe.is_active = True
        pe.save(update_fields=["is_active"])
    return pe


@transaction.atomic
def update_project_employee(
    project: Project,
    employee_id: int,
    *,
    full_name: str | None = None,
    position: str | None = None,
    phone: str | None = None,
    brigade: str | None = None,
    status: str | None = None,
) -> ProjectEmployee:
    pe = (
        ProjectEmployee.objects.filter(
            project=project,
            employee_id=employee_id,
            is_active=True,
        )
        .select_related("employee")
        .first()
    )
    if not pe:
        raise ValueError("employee")

    emp = pe.employee
    if full_name is not None:
        name = full_name.strip()
        if not name:
            raise ValueError("full_name")
        dup = (
            Employee.objects.filter(company=project.company, full_name__iexact=name)
            .exclude(pk=emp.pk)
            .exists()
        )
        if dup:
            raise ValueError("duplicate_name")
        emp.full_name = name
    if position is not None:
        emp.position = position.strip()
    if phone is not None:
        emp.phone = phone.strip()
    if brigade is not None:
        emp.brigade = brigade.strip()
    if status is not None:
        emp.status = _normalize_employee_status(status)
    emp.save()
    return pe


@transaction.atomic
def remove_project_employee(project: Project, employee_id: int) -> bool:
    updated = ProjectEmployee.objects.filter(
        project=project,
        employee_id=employee_id,
        is_active=True,
    ).update(is_active=False)
    if not updated:
        raise ValueError("employee")
    return True


def brigades_for_project(project: Project) -> list[str]:
    qs = (
        Employee.objects.filter(
            project_links__project=project,
            project_links__is_active=True,
            status=Employee.STATUS_ACTIVE,
        )
        .exclude(brigade="")
        .values_list("brigade", flat=True)
        .distinct()
        .order_by("brigade")
    )
    return list(qs)
