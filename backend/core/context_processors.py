from __future__ import annotations

from typing import Any

from django.contrib.auth.models import AnonymousUser
from django.http import HttpRequest

from .access_utils import get_current_company, get_user_permission_codes


def company_context(request: HttpRequest) -> dict[str, Any]:
    user = request.user
    if isinstance(user, AnonymousUser) or not user.is_authenticated:
        return {}

    company = get_current_company(user)
    codes = frozenset()
    if company:
        codes = get_user_permission_codes(user, company)
    return {
        "current_company": company,
        "user_permission_codes": codes,
    }


def impersonation_context(
    request: HttpRequest,
) -> dict[str, Any]:
    if not request.user.is_authenticated:
        return {}
    iid = request.session.get(
        "impersonator_id",
    )
    if not iid:
        return {}
    return {
        "impersonation_active": True,
        "impersonation_admin_username": request.session.get(
            "impersonator_username",
            "",
        ),
    }


def saas_superadmin_context(
    request: HttpRequest,
) -> dict[str, Any]:
    if not request.user.is_authenticated:
        return {
            "is_saas_super_admin": False,
        }
    from .models import UserProfile

    return {
        "is_saas_super_admin": UserProfile.objects.filter(
            user=request.user,
            is_super_admin=True,
        ).exists(),
    }

