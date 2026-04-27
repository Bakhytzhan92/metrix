"""
Проверка доступа к разделам по RBAC (роль в компании + права Permission).
Владелец компании (owner) — полный доступ. Роль «Владелец» (slug owner) — полный доступ.
"""
from __future__ import annotations

from django.contrib.auth import get_user_model

from .models import Company, CompanyRole, CompanyUser
from .rbac import codes_required_for_path

User = get_user_model()


def get_company_user(user, company):
    """Возвращает CompanyUser для пользователя и компании или None."""
    if not user.is_authenticated or not company:
        return None
    return (
        CompanyUser.objects.filter(user=user, company=company)
        .select_related("role")
        .prefetch_related("role__permissions")
        .first()
    )


def get_current_company(user):
    """
    Текущая компания пользователя: сначала владеемая, иначе первая по CompanyUser.
    """
    if not user.is_authenticated:
        return None
    company = Company.objects.filter(owner=user).order_by("id").first()
    if company:
        return company
    cu = CompanyUser.objects.filter(user=user, is_active=True).select_related("company").order_by("id").first()
    return cu.company if cu else None


def is_company_owner(user, company):
    return company and company.owner_id == user.id


def get_user_permission_codes(user, company) -> frozenset[str]:
    """Множество кодов прав пользователя в компании (без учёта view/edit-эквивалентов)."""
    if not user.is_authenticated or not company:
        return frozenset()
    if is_company_owner(user, company):
        from .models import Permission

        return frozenset(Permission.objects.values_list("code", flat=True))

    cu = get_company_user(user, company)
    if not cu or not cu.is_active or not cu.role_id:
        return frozenset()
    role = cu.role
    if role.slug == CompanyRole.SLUG_OWNER:
        from .models import Permission

        return frozenset(Permission.objects.values_list("code", flat=True))

    return frozenset(role.permissions.values_list("code", flat=True))


def has_permission(user, company, code: str) -> bool:
    """Проверка одного права; view_* выполняется и при наличии edit_* для того же ресурса."""
    if not user.is_authenticated or not company:
        return False
    codes = get_user_permission_codes(user, company)
    if code in codes:
        return True
    if code.startswith("view_"):
        suffix = code[5:]
        edit_code = f"edit_{suffix}"
        if edit_code in codes:
            return True
    return False


def has_any_permission(user, company, codes: list[str]) -> bool:
    if not codes:
        return True
    return any(has_permission(user, company, c) for c in codes)


def path_allowed_without_role(path: str) -> bool:
    """
    Если пользователь в компании без роли / без записи CompanyUser — только «мягкие»
    разделы (как раньше: без финансов, отчётов, настроек, складов компании).
    """
    restricted = ("/finance/", "/reports/", "/settings/", "/warehouses/")
    return not any(path.startswith(p) for p in restricted)


def can_access_path(user, company, path: str) -> bool:
    """
    Доступ к URL: владелец компании — да; иначе CompanyUser + RBAC.
    Без привязки к компании разрешены только пути без требований RBAC.
    """
    if not user.is_authenticated:
        return False
    from .models import UserProfile

    if UserProfile.objects.filter(
        user=user,
        is_super_admin=True,
    ).exists():
        return True
    if not company:
        if path in ("/", ""):
            return True
        return codes_required_for_path(path) is None
    if is_company_owner(user, company):
        return True

    company_user = get_company_user(user, company)
    if not company_user or not company_user.is_active:
        return path_allowed_without_role(path)

    if not company_user.role_id:
        return path_allowed_without_role(path)

    required = codes_required_for_path(path)
    if required is None:
        return True

    return has_any_permission(user, company, required)


def can_manage_access(user, company) -> bool:
    """Настройки компании и пользователи: manage_users или владелец компании."""
    if not user.is_authenticated or not company:
        return False
    if is_company_owner(user, company):
        return True
    return has_permission(user, company, "manage_users")
