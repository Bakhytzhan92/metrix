"""
Создание системных ролей компании и привязка владельца.
Вызывается при создании компании и в миграции для существующих компаний.
"""
from __future__ import annotations

from .models import Company, CompanyRole, CompanyUser
from .rbac import sync_all_roles_permissions_for_company


def ensure_company_default_roles(company: Company) -> None:
    """
    Создаёт системные роли компании (если ещё нет), назначает права RBAC,
    привязывает владельца к роли «Владелец компании».
    """
    roles_to_create = [
        (
            CompanyRole.SLUG_OWNER,
            "Владелец компании",
            "Полный доступ ко всем модулям",
        ),
        (
            CompanyRole.SLUG_MANAGER,
            "Руководитель",
            "Полный доступ ко всем модулям",
        ),
        (
            CompanyRole.SLUG_EMPLOYEE,
            "Сотрудник",
            "Доступ ко всем модулям кроме финансов, отчётов и настроек пользователей",
        ),
        (
            CompanyRole.SLUG_PTO,
            "ПТО",
            "Проекты, смета, график работ",
        ),
        (
            CompanyRole.SLUG_SUPPLY,
            "Снабженец",
            "Снабжение и склады",
        ),
        (
            CompanyRole.SLUG_ACCOUNTANT,
            "Бухгалтер",
            "Финансы и отчёты",
        ),
    ]
    for slug, name, description in roles_to_create:
        CompanyRole.objects.get_or_create(
            company=company,
            slug=slug,
            defaults={
                "name": name,
                "description": description,
                "is_system": True,
            },
        )

    sync_all_roles_permissions_for_company(company)

    owner_role = CompanyRole.objects.get(company=company, slug=CompanyRole.SLUG_OWNER)
    CompanyUser.objects.get_or_create(
        user_id=company.owner_id,
        company=company,
        defaults={"role": owner_role, "is_active": True},
    )
