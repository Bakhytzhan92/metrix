"""
Middleware: RBAC по пути запроса.
"""
from __future__ import annotations

from django.http import HttpRequest, HttpResponse

from .access_utils import can_access_path, get_current_company
from .rbac import codes_required_for_path


class AccessControlMiddleware:
    """
    Подставляет текущую компанию и проверяет права для URL с требованиями RBAC.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if not request.user.is_authenticated:
            return self.get_response(request)

        request.current_company = get_current_company(request.user)
        path = request.path

        required = codes_required_for_path(path)
        if required is not None:
            if not can_access_path(request.user, request.current_company, path):
                from django.http import HttpResponseForbidden

                return HttpResponseForbidden(
                    "<h1>403</h1><p>Недостаточно прав для доступа к этому разделу.</p>"
                )

        return self.get_response(request)
