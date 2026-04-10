"""
Проверка доступа к разделам по роли пользователя в компании.
Владелец (company.owner) и роль «Владелец компании» — полный доступ.
Руководитель — полный доступ (чтение/редактирование; read-only можно уточнить на уровне view).
Сотрудник — без доступа к: Финансы, Отчёты, Настройки.
"""
from __future__ import annotations

from django.contrib.auth import get_user_model

from .models import Company, CompanyRole, CompanyUser

User = get_user_model()

# Префиксы URL, доступ к которым ограничивается по ролям
RESTRICTED_FINANCE = "/finance/"
RESTRICTED_REPORTS = "/reports/"
RESTRICTED_SETTINGS = "/settings/"
RESTRICTED_WAREHOUSES = "/warehouses/"

# Для роли «Сотрудник» запрещены только эти разделы
EMPLOYEE_DENIED_PREFIXES = (RESTRICTED_FINANCE, RESTRICTED_REPORTS, RESTRICTED_SETTINGS)


def get_company_user(user, company):
    """Возвращает CompanyUser для пользователя и компании или None."""
    if not user.is_authenticated or not company:
        return None
    return CompanyUser.objects.filter(user=user, company=company).select_related("role").first()


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


def can_access_path(user, company, path: str) -> bool:
    """
    Проверяет, разрешён ли пользователю доступ к данному path (request.path).
    Владелец компании и роль «Владелец» — полный доступ.
    Роль «Руководитель» — полный доступ.
    Роль «Сотрудник» — без доступа к /finance/, /reports/, /settings/.
    Нет роли / не в компании — доступ запрещён для ограниченных разделов.
    """
    if not user.is_authenticated or not company:
        return False

    # Владелец компании всегда имеет полный доступ
    if is_company_owner(user, company):
        return True

    company_user = get_company_user(user, company)
    if not company_user or not company_user.is_active:
        # Нет записи в компании — для ограниченных разделов запрет
        return path_allowed_without_role(path)

    role = company_user.role
    if not role:
        return path_allowed_without_role(path)

    slug = (role.slug or "").strip()
    if slug == CompanyRole.SLUG_OWNER:
        return True
    if slug == CompanyRole.SLUG_MANAGER:
        return True
    if slug == CompanyRole.SLUG_EMPLOYEE:
        return not any(path.startswith(p) for p in EMPLOYEE_DENIED_PREFIXES)

    # Кастомная роль: по умолчанию запрещаем ограниченные разделы
    return not any(path.startswith(p) for p in EMPLOYEE_DENIED_PREFIXES)


def path_allowed_without_role(path: str) -> bool:
    """Доступ к ограниченным путям без роли (только владелец имеет доступ)."""
    restricted = (RESTRICTED_FINANCE, RESTRICTED_REPORTS, RESTRICTED_SETTINGS, RESTRICTED_WAREHOUSES)
    return not any(path.startswith(p) for p in restricted)


def can_manage_access(user, company) -> bool:
    """Может ли пользователь управлять правами (настройки → права доступа). Только владелец или роль Владелец."""
    if not user.is_authenticated or not company:
        return False
    if is_company_owner(user, company):
        return True
    cu = get_company_user(user, company)
    return cu and cu.is_active and cu.role_id and (cu.role.slug == CompanyRole.SLUG_OWNER)
