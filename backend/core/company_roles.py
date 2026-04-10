"""
Создание системных ролей компании и привязка владельца.
Вызывается при создании компании и в миграции для существующих компаний.
"""
from __future__ import annotations

from .models import Company, CompanyRole, CompanyUser


def ensure_company_default_roles(company: Company) -> None:
    """
    Создаёт три системные роли компании (если ещё нет) и привязывает
    владельца компании к роли «Владелец компании».
    """
    roles_to_create = [
        (
            CompanyRole.SLUG_OWNER,
            "Владелец компании",
            "Полный доступ ко всем модулям",
        ),
        (
            CompanyRole.SLUG_MANAGER,
            "Руководитель (только просмотр)",
            "Доступ на чтение ко всем разделам без редактирования",
        ),
        (
            CompanyRole.SLUG_EMPLOYEE,
            "Сотрудник",
            "Доступ ко всем модулям кроме: Отчёты, Финансы, Настройки",
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

    owner_role = CompanyRole.objects.get(company=company, slug=CompanyRole.SLUG_OWNER)
    CompanyUser.objects.get_or_create(
        user_id=company.owner_id,
        company=company,
        defaults={"role": owner_role, "is_active": True},
    )
