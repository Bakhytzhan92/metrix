from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Max
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.shortcuts import render
from django.views.decorators.http import require_POST, require_http_methods

from .access_utils import get_current_company
from .ai_import import process_document
from .models import Project, ProjectSchedulePhase, Task, UploadedDocument

MAX_PDF_BYTES = 10 * 1024 * 1024  # 10 MB


@login_required
def project_ai_import(request: HttpRequest, pk: int) -> HttpResponse:
    """Страница «Умный импорт (PDF + ИИ)» внутри проекта."""
    from .views import _get_project_or_403

    project, err = _get_project_or_403(request, pk)
    if err:
        return err
    recent = (
        UploadedDocument.objects.filter(project=project)
        .order_by("-uploaded_at")[:25]
    )
    return render(
        request,
        "core/project/ai_import.html",
        {
            "project": project,
            "active_tab": "ai",
            "recent_documents": recent,
            "project_type_choices": UploadedDocument.PROJECT_TYPE_CHOICES,
            "max_pdf_mb": MAX_PDF_BYTES // (1024 * 1024),
        },
    )


def _company_project(request: HttpRequest, project_id: int) -> tuple[Project | None, HttpResponse | None]:
    company = get_current_company(request.user)
    if not company:
        return None, JsonResponse({"ok": False, "error": "no_company"}, status=403)
    project = get_object_or_404(Project, pk=project_id, company=company)
    return project, None


def _document_for_user(request: HttpRequest, doc_id: int) -> tuple[UploadedDocument | None, HttpResponse | None]:
    company = get_current_company(request.user)
    if not company:
        return None, JsonResponse({"ok": False, "error": "no_company"}, status=403)
    doc = get_object_or_404(
        UploadedDocument.objects.select_related("project"),
        pk=doc_id,
        project__company=company,
    )
    return doc, None


@login_required
@require_POST
def api_upload_pdf(request: HttpRequest) -> HttpResponse:
    """POST multipart: project_id, project_type (optional), file."""
    try:
        project_id = int(request.POST.get("project_id") or "0")
    except ValueError:
        return JsonResponse({"ok": False, "error": "invalid_project_id"}, status=400)
    project, err = _company_project(request, project_id)
    if err:
        return err

    f = request.FILES.get("file")
    if not f:
        return JsonResponse({"ok": False, "error": "file_required"}, status=400)
    if f.size > MAX_PDF_BYTES:
        return JsonResponse(
            {
                "ok": False,
                "error": "file_too_large",
                "max_mb": MAX_PDF_BYTES // (1024 * 1024),
            },
            status=400,
        )
    if not (f.name or "").lower().endswith(".pdf"):
        return JsonResponse({"ok": False, "error": "pdf_only"}, status=400)

    ptype = request.POST.get("project_type") or UploadedDocument.TYPE_RESIDENTIAL
    if ptype not in dict(UploadedDocument.PROJECT_TYPE_CHOICES):
        ptype = UploadedDocument.TYPE_RESIDENTIAL

    doc = UploadedDocument.objects.create(
        project=project,
        file=f,
        uploaded_by=request.user,
        project_type=ptype,
        status=UploadedDocument.STATUS_UPLOADED,
    )
    process_document(doc.pk)
    doc.refresh_from_db()
    return JsonResponse(
        {
            "ok": doc.status == UploadedDocument.STATUS_DONE,
            "id": doc.pk,
            "status": doc.status,
            "error": doc.error_message
            if doc.status == UploadedDocument.STATUS_ERROR
            else None,
        },
        status=200 if doc.status != UploadedDocument.STATUS_ERROR else 422,
    )


@login_required
@require_http_methods(["GET"])
def api_document_detail(request: HttpRequest, doc_id: int) -> HttpResponse:
    doc, err = _document_for_user(request, doc_id)
    if err:
        return err
    return JsonResponse(
        {
            "ok": True,
            "id": doc.pk,
            "status": doc.status,
            "project_id": doc.project_id,
            "project_type": doc.project_type,
            "ai_result": doc.ai_result,
            "error_message": doc.error_message or None,
            "uploaded_at": doc.uploaded_at.isoformat(),
        }
    )


def _apply_ai_plan_to_project(doc: UploadedDocument, user) -> dict[str, Any]:
    """Создаёт этапы графика и задачи по ai_result. Возвращает счётчики."""
    data = doc.ai_result or {}
    stages = data.get("stages")
    if not isinstance(stages, list) or not stages:
        raise ValueError("Нет данных этапов (ai_result.stages)")

    project = doc.project
    start = project.start_date or timezone.now().date()
    agg = ProjectSchedulePhase.objects.filter(project=project).aggregate(
        m=Max("order")
    )
    max_order = agg.get("m") or 0
    phase_order = int(max_order)
    predecessor: ProjectSchedulePhase | None = None
    phases_created = 0
    tasks_created = 0

    with transaction.atomic():
        cursor = start
        for stage in stages:
            if not isinstance(stage, dict):
                continue
            name = (stage.get("name") or "").strip() or "Этап"
            tasks_raw = stage.get("tasks") or []
            if not isinstance(tasks_raw, list):
                tasks_raw = []

            duration_days = 0
            for t in tasks_raw:
                if isinstance(t, dict):
                    try:
                        d = int(t.get("duration_days") or 1)
                    except (TypeError, ValueError):
                        d = 1
                    duration_days += max(1, d)
            if duration_days < 1:
                duration_days = 1

            phase_start = cursor
            phase_end = phase_start + timedelta(days=duration_days - 1)
            phase_order += 1
            phase = ProjectSchedulePhase.objects.create(
                project=project,
                name=name[:255],
                start_date=phase_start,
                end_date=phase_end,
                order=phase_order,
                predecessor=predecessor,
                status=ProjectSchedulePhase.STATUS_PLANNED,
            )
            predecessor = phase
            phases_created += 1
            cursor = phase_end + timedelta(days=1)

            for t in tasks_raw:
                if not isinstance(t, dict):
                    continue
                tname = (t.get("name") or "").strip() or "Задача"
                ttype = (t.get("type") or "labor").strip()
                deps = t.get("depends_on") or []
                if not isinstance(deps, list):
                    deps = []
                desc = f"Тип: {ttype}\nИмпорт ИИ (документ #{doc.pk})"
                if deps:
                    desc += "\nЗависимости: " + ", ".join(str(x) for x in deps)
                try:
                    td = int(t.get("duration_days") or 1)
                except (TypeError, ValueError):
                    td = 1
                td = max(1, td)
                due = phase_start + timedelta(days=td - 1)
                if due > phase_end:
                    due = phase_end
                Task.objects.create(
                    project=project,
                    title=tname[:255],
                    description=desc,
                    created_by=user,
                    start_date=phase_start,
                    due_date=due,
                )
                tasks_created += 1

    return {"phases": phases_created, "tasks": tasks_created}


@login_required
@require_POST
def api_document_apply(request: HttpRequest, doc_id: int) -> HttpResponse:
    """Создаёт этапы графика и задачи только после явного подтверждения."""
    doc, err = _document_for_user(request, doc_id)
    if err:
        return err
    if doc.status != UploadedDocument.STATUS_DONE:
        return JsonResponse(
            {"ok": False, "error": "document_not_ready", "status": doc.status},
            status=400,
        )
    try:
        stats = _apply_ai_plan_to_project(doc, request.user)
    except ValueError as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=400)
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)[:500]}, status=500)
    return JsonResponse({"ok": True, **stats})
