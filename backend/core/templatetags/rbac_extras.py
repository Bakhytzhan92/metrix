"""Теги шаблонов для проверки прав RBAC."""
from __future__ import annotations

from django import template

from core.access_utils import get_current_company, has_permission

register = template.Library()


@register.simple_tag(takes_context=True)
def has_perm(context, code: str) -> bool:
    request = context.get("request")
    if not request or not request.user.is_authenticated:
        return False
    company = getattr(request, "current_company", None) or get_current_company(request.user)
    return has_permission(request.user, company, code)
