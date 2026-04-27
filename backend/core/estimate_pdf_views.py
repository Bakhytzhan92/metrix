from __future__ import annotations

import json
from typing import Any

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.http import require_http_methods, require_POST

from .access_utils import get_current_company
from .estimate_pdf_service import apply_local_estimate_rows
from .models import Project

try:
    from .services.local_estimate_parser import parse_local_estimate
except ImportError:
    parse_local_estimate = None  # type: ignore[misc, assignment]


def _json_err(
    msg: str, code: int = 400, **extra: Any
) -> JsonResponse:
    p: dict[str, Any] = {
        "ok": False, "error": msg
    }
    p.update(
        extra
    )
    return JsonResponse(
        p, status=code
    )


def _get_project(
    request: HttpRequest, pk: int
) -> tuple[Project | None, JsonResponse | None]:
    company = get_current_company(
        request.user
    )
    if not company:
        return None, _json_err(
            "Сначала выберите компанию", 401
        )
    try:
        project = Project.objects.get(
            pk=pk
        )
    except Project.DoesNotExist:
        return None, _json_err(
            "Проект не найден", 404
        )
    if project.company_id != company.id:
        return None, _json_err(
            "Проект не принадлежит вашей компании",
            403,
        )
    return project, None


@login_required
@require_http_methods(
    [
        "POST",
    ]
)
def api_estimate_import_pdf(
    request: HttpRequest,
) -> HttpResponse:
    """
    POST: multipart: file, project_id
    JSON: { ok, rows: [ { section, name, unit, quantity } ] }
    """
    if not parse_local_estimate:
        return _json_err(
            "Парсер PDF недоступен",
            500,
        )
    from django.core.exceptions import ValidationError

    project_id = request.POST.get("project_id")
    f = request.FILES.get("file")
    if not f or not project_id:
        return _json_err(
            "Нужны project_id и file (PDF).",
        )
    if not (
        f.name or ""
    ).lower().endswith(
        ".pdf"
    ):
        return _json_err(
            "Ожидается файл .pdf",
        )
    try:
        pk = int(
            project_id
        )
    except (TypeError, ValueError):
        return _json_err(
            "Некорректный project_id",
        )
    project, perr = _get_project(
        request, pk
    )
    if perr is not None:
        return perr
    try:
        rows = parse_local_estimate(
            f
        )
    except (
        OSError, ValidationError, ValueError
    ) as e:  # noqa: BLE001
        return _json_err(
            str(
                e
            ) or "Ошибка чтения PDF",
        )
    return JsonResponse(
        {
            "ok": True,
            "rows": rows,
            "count": len(
                rows
            ),
        }
    )


@login_required
@require_POST
def api_estimate_import_pdf_apply(
    request: HttpRequest,
) -> HttpResponse:
    if request.content_type and "json" in request.content_type:
        try:
            body = json.loads(
                request.body.decode(
                    "utf-8"
                )
            )
        except (json.JSONDecodeError, ValueError) as e:
            return _json_err(
                f"JSON: {e}"
            )
    else:
        return _json_err(
            "Ожидается application/json"
        )
    project_id = body.get(
        "project_id"
    )
    rows = body.get(
        "rows", []
    )
    if not isinstance(
        rows, list
    ):
        return _json_err(
            "rows — массив"
        )
    try:
        pk = int(
            project_id
        )
    except (TypeError, ValueError):
        return _json_err(
            "project_id"
        )
    project, perr = _get_project(
        request, pk
    )
    if perr is not None:
        return perr
    result = apply_local_estimate_rows(
        project, rows
    )
    return JsonResponse(
        {
            "ok": True,
            "items_created": result["items_created"],
            "errors": result.get(
                "errors", []
            ),
        }
    )


@login_required
@require_http_methods(
    [
        "POST",
    ]
)
def api_estimate_import_pdf_apply_file(
    request: HttpRequest,
) -> HttpResponse:
    """
    Один запрос: multipart file + project_id → разбор PDF и запись в смету.
    Без передачи тысяч строк JSON в браузер (обходит лимиты тела запроса).
    """
    if not parse_local_estimate:
        return _json_err(
            "Парсер PDF недоступен",
            500,
        )
    from django.core.exceptions import ValidationError

    project_id = request.POST.get(
        "project_id"
    )
    f = request.FILES.get(
        "file"
    )
    if not f or not project_id:
        return _json_err(
            "Нужны project_id и file (PDF).",
        )
    if not (
        f.name or ""
    ).lower().endswith(
        ".pdf"
    ):
        return _json_err(
            "Ожидается файл .pdf",
        )
    try:
        pk = int(
            project_id
        )
    except (TypeError, ValueError):
        return _json_err(
            "Некорректный project_id",
        )
    project, perr = _get_project(
        request, pk
    )
    if perr is not None:
        return perr
    try:
        rows = parse_local_estimate(
            f
        )
    except (
        OSError, ValidationError, ValueError
    ) as e:  # noqa: BLE001
        return _json_err(
            str(
                e
            )
            or "Ошибка чтения PDF",
        )
    result = apply_local_estimate_rows(
        project, rows
    )
    return JsonResponse(
        {
            "ok": True,
            "items_created": result["items_created"],
            "count_parsed": len(
                rows
            ),
            "errors": result.get(
                "errors", []
            ),
        }
    )
