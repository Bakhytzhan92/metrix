from __future__ import annotations

from typing import Any

from django.contrib.auth.models import AnonymousUser
from django.http import HttpRequest

from .access_utils import get_current_company


def company_context(request: HttpRequest) -> dict[str, Any]:
    user = request.user
    if isinstance(user, AnonymousUser) or not user.is_authenticated:
        return {}

    company = get_current_company(user)
    return {"current_company": company}

