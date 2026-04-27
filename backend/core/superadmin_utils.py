"""
Доступ супер-администратора платформы и журнал действий.
"""
from __future__ import annotations

import functools
import json

from django.http import HttpResponseForbidden, JsonResponse

from .models import ActivityLog, UserProfile


def log_saas_activity(
    request,
    action: str,
    entity: str,
    entity_id: str = "",
    meta: dict | None = None,
) -> None:
    if not request.user.is_authenticated:
        return
    ActivityLog.objects.create(
        user=request.user,
        action=action,
        entity=entity,
        entity_id=str(
            entity_id,
        )
        if entity_id is not None
        else "",
        meta=meta or {},
    )


def super_admin_required(
    view_func,
):
    @functools.wraps(
        view_func,
    )
    def wrapper(
        request,
        *args,
        **kwargs,
    ):
        if not request.user.is_authenticated:
            if request.path.startswith(
                "/api/superadmin/",
            ):
                return JsonResponse(
                    {
                        "ok": False,
                        "error": "Требуется вход",
                    },
                    status=401,
                )
            from django.contrib.auth.views import redirect_to_login

            return redirect_to_login(
                request.get_full_path(),
            )

        if request.session.get(
            "impersonator_id",
        ):
            msg = "Недоступно во время имперсонации. Выйдите из аккаунта пользователя."
            if request.path.startswith(
                "/api/superadmin/",
            ):
                return JsonResponse(
                    {
                        "ok": False,
                        "error": msg,
                    },
                    status=403,
                )
            return HttpResponseForbidden(
                msg,
            )

        if not UserProfile.objects.filter(
            user=request.user,
            is_super_admin=True,
        ).exists():
            if request.path.startswith(
                "/api/superadmin/",
            ):
                return JsonResponse(
                    {
                        "ok": False,
                        "error": "Нет доступа",
                    },
                    status=403,
                )
            return HttpResponseForbidden(
                "Нет доступа",
            )

        return view_func(
            request,
            *args,
            **kwargs,
        )

    return wrapper


def parse_json_body(
    request,
) -> dict:
    if not request.body:
        return {}
    try:
        return json.loads(
            request.body.decode(
                "utf-8",
            ),
        )
    except (
        ValueError,
        UnicodeDecodeError,
    ):
        return {}
