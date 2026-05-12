from __future__ import annotations

import json
import logging
import math
from typing import Any

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.http import require_http_methods, require_POST

from .access_utils import get_current_company
from .estimate_pdf_service import apply_local_estimate_rows
from .models import Project

logger = logging.getLogger(__name__)

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


def _sanitize_rows_for_json(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Убираем NaN/inf у quantity — иначе JsonResponse может упасть с 500."""
    out: list[dict[str, Any]] = []
    for r in rows:
        if not isinstance(
            r,
            dict,
        ):
            continue
        d = dict(r)
        q = d.get("quantity")
        if isinstance(
            q,
            float,
        ):
            if math.isnan(q) or math.isinf(q):
                d["quantity"] = 0.0
        elif q is not None and not isinstance(
            q,
            (int, float, str),
        ):
            try:
                d["quantity"] = float(q)
            except (TypeError, ValueError):
                d["quantity"] = 0.0
        out.append(d)
    return out


def _parse_pdf_safe(
    uploaded,
) -> tuple[list[dict[str, Any]] | None, JsonResponse | None]:
    """Разбор PDF; любая ошибка парсера → JSON-ответ, не HTML 500."""
    from django.core.exceptions import ValidationError

    if not parse_local_estimate:
        return None, _json_err(
            "Парсер PDF недоступен (не установлены зависимости).",
            500,
        )
    try:
        rows = parse_local_estimate(
            uploaded,
        )
    except (
        OSError,
        ValidationError,
        ValueError,
        TypeError,
    ) as e:
        return None, _json_err(
            str(e) or "Ошибка чтения PDF",
        )
    except Exception as e:
        logger.exception(
            "parse_local_estimate failed",
        )
        if settings.DEBUG:
            return None, _json_err(
                f"Разбор PDF: {e}",
                500,
            )
        return None, _json_err(
            "Не удалось разобрать PDF (повреждённый или неподдерживаемый файл). "
            "Попробуйте экспортировать PDF заново или другой файл.",
            500,
        )
    if not isinstance(
        rows,
        list,
    ):
        return None, _json_err(
            "Внутренняя ошибка: парсер вернул не список строк",
            500,
        )
    try:
        safe = _sanitize_rows_for_json(
            rows,
        )
    except Exception:
        logger.exception(
            "sanitize rows after PDF parse",
        )
        return None, _json_err(
            "Ошибка подготовки данных сметы",
            500,
        )
    return safe, None


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
    rows, err = _parse_pdf_safe(
        f
    )
    if err is not None:
        return err
    return JsonResponse(
        {
            "ok": True,
            "rows": rows,
            "count": len(
                rows or [],
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
    try:
        result = apply_local_estimate_rows(
            project, rows
        )
    except Exception:
        logger.exception(
            "apply_local_estimate_rows failed",
        )
        if settings.DEBUG:
            return _json_err(
                "Ошибка записи в смету (см. лог сервера).",
                500,
            )
        return _json_err(
            "Не удалось сохранить импорт. Попробуйте ещё раз или меньший объём данных.",
            500,
        )
    return JsonResponse(
        {
            "ok": True,
            "items_created": result["items_created"],
            "count_parsed": len(rows),
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
    rows, parse_err = _parse_pdf_safe(
        f
    )
    if parse_err is not None:
        return parse_err
    try:
        result = apply_local_estimate_rows(
            project,
            rows or [],
        )
    except Exception:
        logger.exception(
            "apply_local_estimate_rows failed (apply-file)",
        )
        if settings.DEBUG:
            return _json_err(
                "Ошибка записи в смету (см. лог сервера).",
                500,
            )
        return _json_err(
            "Не удалось сохранить импорт. Попробуйте ещё раз.",
            500,
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
