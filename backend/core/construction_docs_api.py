"""
JSON API раздела «Документы» проекта: папки, файлы, загрузка.
Права: просмотр — view_projects, загрузка и правки — edit_projects.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime
from typing import Any

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET, require_http_methods

from .access_utils import has_permission
from .models import ProjectConstructionFile, ProjectDocumentFolder, Project
from .rbac import permission_required

ALLOWED_EXTENSIONS = {".pdf", ".doc", ".docx", ".xlsx", ".jpg", ".jpeg", ".png"}


def _json(body: dict[str, Any], status: int = 200) -> JsonResponse:
    return JsonResponse(body, status=status, json_dumps_params={"ensure_ascii": False})


def _parse_date(s: str | None):
    if not s:
        return None
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def detect_file_kind(ext: str) -> str:
    e = (ext or "").lower()
    if e == ".pdf":
        return ProjectConstructionFile.KIND_PDF
    if e in (".doc", ".docx"):
        return ProjectConstructionFile.KIND_WORD
    if e == ".xlsx":
        return ProjectConstructionFile.KIND_SPREADSHEET
    if e in (".jpg", ".jpeg", ".png"):
        return ProjectConstructionFile.KIND_IMAGE
    return ProjectConstructionFile.KIND_OTHER


def suggest_category_from_filename(filename: str) -> str:
    fn = (filename or "").lower()
    if "аоср" in fn:
        return ProjectConstructionFile.CATEGORY_AOSR
    if "исполнительн" in fn and ("схем" in fn or "схема" in fn):
        return ProjectConstructionFile.CATEGORY_EXEC_SCHEME
    if "исполнительная схема" in fn:
        return ProjectConstructionFile.CATEGORY_EXEC_SCHEME
    if "акт" in fn:
        return ProjectConstructionFile.CATEGORY_AOSR
    if "договор" in fn:
        return ProjectConstructionFile.CATEGORY_CONTRACT
    if "чертеж" in fn:
        return ProjectConstructionFile.CATEGORY_DRAWING
    return ProjectConstructionFile.CATEGORY_GENERAL


def suggest_category_from_extension(ext: str) -> str | None:
    k = detect_file_kind(ext)
    if k == ProjectConstructionFile.KIND_WORD:
        return ProjectConstructionFile.CATEGORY_GENERAL
    if k == ProjectConstructionFile.KIND_PDF:
        return ProjectConstructionFile.CATEGORY_GENERAL
    if k == ProjectConstructionFile.KIND_IMAGE:
        return ProjectConstructionFile.CATEGORY_GENERAL
    return None


def _get_project(request: HttpRequest, pk: int):
    from .views import _get_project_or_403

    return _get_project_or_403(request, pk)


def _serialize_folder(f: ProjectDocumentFolder) -> dict[str, Any]:
    return {
        "id": f.id,
        "parent_id": f.parent_id,
        "name": f.name,
        "created_at": f.created_at.isoformat(),
    }


def _build_folder_tree(project: Project) -> list[dict[str, Any]]:
    rows = list(
        ProjectDocumentFolder.objects.filter(project=project).order_by(
            "parent_id", "name"
        )
    )
    by_parent: dict[int | None, list[ProjectDocumentFolder]] = {}
    for f in rows:
        by_parent.setdefault(f.parent_id, []).append(f)

    def nest(parent_id: int | None) -> list[dict[str, Any]]:
        out = []
        for f in by_parent.get(parent_id, []):
            d = _serialize_folder(f)
            d["children"] = nest(f.id)
            out.append(d)
        return out

    return nest(None)


def _serialize_file(
    request: HttpRequest, obj: ProjectConstructionFile
) -> dict[str, Any]:
    url = ""
    if obj.file:
        url = request.build_absolute_uri(obj.file.url)
    size = 0
    try:
        if obj.file:
            size = obj.file.size
    except (OSError, ValueError):
        pass
    return {
        "id": obj.id,
        "title": obj.title,
        "original_filename": obj.original_filename,
        "file_kind": obj.file_kind,
        "file_kind_display": obj.get_file_kind_display(),
        "category": obj.category,
        "category_display": obj.get_category_display(),
        "workflow_status": obj.workflow_status,
        "workflow_status_display": obj.get_workflow_status_display(),
        "size": size,
        "size_display": _format_size(size),
        "uploaded_by": obj.uploaded_by.get_username() if obj.uploaded_by else None,
        "created_at": obj.created_at.isoformat(),
        "updated_at": obj.updated_at.isoformat(),
        "act_number": obj.act_number,
        "act_date": obj.act_date.isoformat() if obj.act_date else None,
        "work_section": obj.work_section,
        "folder_id": obj.folder_id,
        "file_url": url,
    }


def _format_size(n: int) -> str:
    if n < 1024:
        return f"{n} Б"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} КБ"
    return f"{n / (1024 * 1024):.1f} МБ"


def _apply_tab_filter(qs, tab: str):
    tab = (tab or "all").strip().lower()
    if tab == "aosr":
        return qs.filter(category=ProjectConstructionFile.CATEGORY_AOSR)
    if tab == "exec_schemes":
        return qs.filter(category=ProjectConstructionFile.CATEGORY_EXEC_SCHEME)
    if tab == "contracts":
        return qs.filter(category=ProjectConstructionFile.CATEGORY_CONTRACT)
    if tab == "drawings":
        return qs.filter(category=ProjectConstructionFile.CATEGORY_DRAWING)
    if tab == "pdf":
        return qs.filter(file_kind=ProjectConstructionFile.KIND_PDF)
    if tab == "word":
        return qs.filter(file_kind=ProjectConstructionFile.KIND_WORD)
    if tab == "photos":
        return qs.filter(file_kind=ProjectConstructionFile.KIND_IMAGE)
    if tab == "archive":
        return qs.filter(workflow_status=ProjectConstructionFile.WORKFLOW_ARCHIVE)
    return qs


@login_required
@require_GET
@permission_required("view_projects")
def api_construction_folders_tree(request: HttpRequest, pk: int) -> JsonResponse:
    project, err = _get_project(request, pk)
    if err:
        return err
    tree = _build_folder_tree(project)
    flat = list(
        ProjectDocumentFolder.objects.filter(project=project).values(
            "id", "parent_id", "name"
        )
    )
    return _json({"ok": True, "tree": tree, "flat": flat})


@login_required
@require_http_methods(["POST"])
@permission_required("view_projects")
def api_construction_folder_create(request: HttpRequest, pk: int) -> JsonResponse:
    project, err = _get_project(request, pk)
    if err:
        return err
    if not has_permission(request.user, project.company, "edit_projects"):
        return _json({"ok": False, "error": "forbidden"}, status=403)
    try:
        body = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return _json({"ok": False, "error": "bad_json"}, status=400)
    name = (body.get("name") or "").strip()[:255]
    if not name:
        return _json({"ok": False, "error": "name_required"}, status=400)
    parent_id = body.get("parent_id")
    parent = None
    if parent_id is not None and str(parent_id).isdigit():
        parent = get_object_or_404(
            ProjectDocumentFolder, pk=int(parent_id), project=project
        )
    f = ProjectDocumentFolder.objects.create(
        project=project, parent=parent, name=name
    )
    return _json({"ok": True, "folder": _serialize_folder(f)})


@login_required
@require_GET
@permission_required("view_projects")
def api_construction_files_list(request: HttpRequest, pk: int) -> JsonResponse:
    project, err = _get_project(request, pk)
    if err:
        return err

    tab = (request.GET.get("tab") or "all").strip()
    q = (request.GET.get("q") or "").strip()
    kind = (request.GET.get("kind") or "").strip()
    category = (request.GET.get("category") or "").strip()
    folder_raw = request.GET.get("folder_id")
    folder_id: int | None = None
    if folder_raw and str(folder_raw).isdigit():
        folder_id = int(folder_raw)

    qs = ProjectConstructionFile.objects.filter(project=project).select_related(
        "uploaded_by", "folder"
    )

    qs = _apply_tab_filter(qs, tab)
    if folder_id is not None:
        qs = qs.filter(folder_id=folder_id)
    if q:
        qs = qs.filter(
            Q(title__icontains=q)
            | Q(original_filename__icontains=q)
            | Q(act_number__icontains=q)
        )
    if kind and kind in dict(ProjectConstructionFile.KIND_CHOICES):
        qs = qs.filter(file_kind=kind)
    if category and category in dict(ProjectConstructionFile.CATEGORY_CHOICES):
        qs = qs.filter(category=category)

    qs = qs.order_by("-updated_at")[:2000]
    rows = [_serialize_file(request, o) for o in qs]
    return _json({"ok": True, "files": rows})


@login_required
@require_http_methods(["POST"])
@permission_required("view_projects")
def api_construction_files_upload(request: HttpRequest, pk: int) -> JsonResponse:
    project, err = _get_project(request, pk)
    if err:
        return err
    if not has_permission(request.user, project.company, "edit_projects"):
        return _json({"ok": False, "error": "forbidden"}, status=403)

    folder_id = request.POST.get("folder_id")
    folder = None
    if folder_id and str(folder_id).isdigit():
        folder = get_object_or_404(
            ProjectDocumentFolder, pk=int(folder_id), project=project
        )

    files = request.FILES.getlist("files")
    if not files:
        return _json({"ok": False, "error": "no_files"}, status=400)

    created = []
    errors: list[str] = []
    for f in files:
        orig = (f.name or "file").strip() or "file"
        _, ext = os.path.splitext(orig)
        ext_l = ext.lower()
        if ext_l not in ALLOWED_EXTENSIONS:
            errors.append(f"{orig}: недопустимый тип файла")
            continue
        kind = detect_file_kind(ext_l)
        cat = suggest_category_from_filename(orig)
        if cat == ProjectConstructionFile.CATEGORY_GENERAL:
            ext_hint = suggest_category_from_extension(ext_l)
            if ext_hint:
                cat = ext_hint
        obj = ProjectConstructionFile(
            project=project,
            folder=folder,
            original_filename=orig[:255],
            title=os.path.basename(orig)[:255],
            file_kind=kind,
            category=cat,
            workflow_status=ProjectConstructionFile.WORKFLOW_DRAFT,
            uploaded_by=request.user,
        )
        if cat == ProjectConstructionFile.CATEGORY_AOSR:
            m = re.search(
                r"(?:акт|аоср)\s*[№#]?\s*([0-9a-zа-яё./\-]+)", orig, re.I
            )
            if m:
                obj.act_number = m.group(1)[:120]
        obj.file.save(orig, f, save=False)
        obj.save()
        created.append(_serialize_file(request, obj))

    return _json(
        {
            "ok": True,
            "created": created,
            "errors": errors,
        },
        status=200,
    )


@login_required
@require_http_methods(["PATCH", "DELETE"])
@permission_required("view_projects")
def api_construction_file_detail(
    request: HttpRequest, pk: int, file_id: int
) -> JsonResponse:
    project, err = _get_project(request, pk)
    if err:
        return err
    obj = get_object_or_404(ProjectConstructionFile, pk=file_id, project=project)

    if request.method == "DELETE":
        if not has_permission(request.user, project.company, "edit_projects"):
            return _json({"ok": False, "error": "forbidden"}, status=403)
        obj.file.delete(save=False)
        obj.delete()
        return _json({"ok": True})

    if not has_permission(request.user, project.company, "edit_projects"):
        return _json({"ok": False, "error": "forbidden"}, status=403)
    try:
        body = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return _json({"ok": False, "error": "bad_json"}, status=400)

    if "title" in body:
        obj.title = (body.get("title") or "")[:255] or obj.title
    if "category" in body and body.get("category") in dict(
        ProjectConstructionFile.CATEGORY_CHOICES
    ):
        obj.category = body["category"]
    if "workflow_status" in body and body.get("workflow_status") in dict(
        ProjectConstructionFile.WORKFLOW_CHOICES
    ):
        obj.workflow_status = body["workflow_status"]
    if "folder_id" in body:
        fid = body.get("folder_id")
        if fid is None or fid == "":
            obj.folder = None
        elif str(fid).isdigit():
            obj.folder = get_object_or_404(
                ProjectDocumentFolder, pk=int(fid), project=project
            )
    if "act_number" in body:
        obj.act_number = (body.get("act_number") or "")[:120]
    if "act_date" in body:
        raw = body.get("act_date")
        if raw in (None, "", "null"):
            obj.act_date = None
        else:
            obj.act_date = _parse_date(str(raw)[:10])
    if "work_section" in body:
        obj.work_section = (body.get("work_section") or "")[:255]
    obj.save()
    return _json({"ok": True, "file": _serialize_file(request, obj)})


@login_required
@require_GET
@permission_required("view_projects")
def api_construction_meta(request: HttpRequest, pk: int) -> JsonResponse:
    project, err = _get_project(request, pk)
    if err:
        return err
    can_edit = has_permission(request.user, project.company, "edit_projects")
    return _json(
        {
            "ok": True,
            "can_edit": can_edit,
            "kinds": [
                {"value": k, "label": str(v)}
                for k, v in ProjectConstructionFile.KIND_CHOICES
            ],
            "categories": [
                {"value": k, "label": str(v)}
                for k, v in ProjectConstructionFile.CATEGORY_CHOICES
            ],
            "statuses": [
                {"value": k, "label": str(v)}
                for k, v in ProjectConstructionFile.WORKFLOW_CHOICES
            ],
        }
    )
