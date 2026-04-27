"""
Блокировка доступа к приложению при отключённом аккаунте / истёкшем trial.
Супер-админ платформы (без имперсонации) не блокируется.
"""
from __future__ import annotations

from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.template.loader import render_to_string

from .access_utils import get_current_company
from .subscription_limits import (
    is_effective_platform_super_admin,
    platform_block_reason,
)


def _exempt_path(
    path: str,
) -> bool:
    if path.startswith(
        "/admin/",
    ) or path.startswith(
        "/accounts/",
    ):
        return True
    if path.startswith(
        "/static/",
    ) or path.startswith(
        "/media/",
    ):
        return True
    if path.startswith(
        "/superadmin/",
    ) or path.startswith(
        "/api/superadmin/",
    ):
        return True
    return False


class PlatformAccountMiddleware:
    def __init__(
        self,
        get_response,
    ):
        self.get_response = get_response

    def __call__(
        self,
        request: HttpRequest,
    ) -> HttpResponse:
        if _exempt_path(
            request.path,
        ):
            return self.get_response(
                request,
            )
        if not request.user.is_authenticated:
            return self.get_response(
                request,
            )
        if is_effective_platform_super_admin(
            request,
        ):
            return self.get_response(
                request,
            )

        company = getattr(
            request,
            "current_company",
            None,
        ) or get_current_company(
            request.user,
        )
        reason = platform_block_reason(
            company,
        )
        if reason:
            accept = (
                request.headers.get(
                    "Accept",
                )
                or ""
            ) + (
                request.headers.get(
                    "X-Requested-With",
                )
                or ""
            )
            if "application/json" in accept or request.path.startswith(
                "/api/",
            ):
                from django.http import JsonResponse

                return JsonResponse(
                    {
                        "ok": False,
                        "error": "account_blocked",
                        "detail": reason,
                    },
                    status=403,
                )
            html = render_to_string(
                "core/platform_blocked.html",
                {
                    "reason": reason,
                },
                request=request,
            )
            return HttpResponseForbidden(
                html,
            )

        return self.get_response(
            request,
        )
