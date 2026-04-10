"""
Middleware: проверка доступа к разделам по роли (Финансы, Отчёты, Настройки, Склады).
"""
from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect

from .access_utils import can_access_path, get_current_company


class AccessControlMiddleware:
    """
    После AuthenticationMiddleware подставляет текущую компанию и проверяет путь.
    Если доступ запрещён — редирект на главную или 403.
    """

    RESTRICTED_PREFIXES = ("/finance/", "/reports/", "/settings/", "/warehouses/")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if not request.user.is_authenticated:
            return self.get_response(request)

        request.current_company = get_current_company(request.user)

        path = request.path
        if any(path.startswith(p) for p in self.RESTRICTED_PREFIXES):
            if not can_access_path(request.user, request.current_company, path):
                from django.http import HttpResponseForbidden
                return HttpResponseForbidden(
                    "<h1>403</h1><p>Недостаточно прав для доступа к этому разделу.</p>"
                )

        return self.get_response(request)
