"""
Лимиты тарифов, пробный период и блокировка аккаунта компании.
"""
from __future__ import annotations

from datetime import date, timedelta

from .models import Company, CompanyUser, Project, Tariff, UserProfile


def is_effective_platform_super_admin(
    request,
) -> bool:
    """Супер-админ без режима имперсонации — обходит блокировки аккаунта."""
    if not request.user.is_authenticated:
        return False
    if request.session.get(
        "impersonator_id",
    ):
        return False
    return UserProfile.objects.filter(
        user=request.user,
        is_super_admin=True,
    ).exists()


def resolve_company_tariff(
    company: Company,
) -> Tariff | None:
    if company.tariff_id:
        return company.tariff
    return (
        Tariff.objects.filter(
            name__iexact=company.subscription_plan,
        ).first()
    )


def refresh_account_status_from_dates(
    company: Company,
) -> bool:
    """
    Если истёк срок подписки — статус trial/active → expired.
    Возвращает True, если объект сохранён.
    """
    if (
        company.subscription_expires_at
        and company.subscription_expires_at < date.today()
        and company.account_status
        in (
            Company.STATUS_TRIAL,
            Company.STATUS_ACTIVE,
        )
    ):
        company.account_status = Company.STATUS_EXPIRED
        company.save(
            update_fields=["account_status"],
        )
        return True
    return False


def platform_block_reason(
    company: Company | None,
) -> str | None:
    """Текст причины блокировки или None, если доступ разрешён."""
    if not company:
        return None
    refresh_account_status_from_dates(
        company,
    )
    if not company.is_active:
        return "Аккаунт компании отключён администратором платформы."
    if company.account_status == Company.STATUS_BLOCKED:
        return "Аккаунт заблокирован."
    if company.account_status == Company.STATUS_EXPIRED:
        return "Пробный период или подписка истекли. Обновите тариф."
    return None


def count_company_projects(
    company: Company,
) -> int:
    return Project.objects.filter(
        company=company,
    ).count()


def count_company_seats(
    company: Company,
) -> int:
    return CompanyUser.objects.filter(
        company=company,
        is_active=True,
    ).count()


def tariff_max_projects(
    company: Company,
) -> int:
    t = resolve_company_tariff(
        company,
    )
    return t.max_projects if t else 0


def tariff_max_users(
    company: Company,
) -> int:
    t = resolve_company_tariff(
        company,
    )
    return t.max_users if t else 0


def can_create_project(
    company: Company,
) -> tuple[bool, str | None]:
    if platform_block_reason(
        company,
    ):
        return False, platform_block_reason(
            company,
        )
    cap = tariff_max_projects(
        company,
    )
    if cap == 0:
        return True, None
    n = count_company_projects(
        company,
    )
    if n >= cap:
        return (
            False,
            f"Достигнут лимит тарифа: максимум {cap} проект(ов).",
        )
    return True, None


def can_add_company_user(
    company: Company,
) -> tuple[bool, str | None]:
    if platform_block_reason(
        company,
    ):
        return False, platform_block_reason(
            company,
        )
    cap = tariff_max_users(
        company,
    )
    if cap == 0:
        return True, None
    n = count_company_seats(
        company,
    )
    if n >= cap:
        return (
            False,
            f"Достигнут лимит тарифа: максимум {cap} пользовател(ей) в компании.",
        )
    return True, None


def apply_trial_for_new_company(
    company: Company,
    tariff: Tariff | None = None,
) -> None:
    """Назначить trial по тарифу (дата окончания + статус)."""
    t = tariff or resolve_company_tariff(
        company,
    )
    if not t:
        t = Tariff.objects.filter(
            name__iexact="Free",
        ).first()
    days = (
        t.trial_days
        if t
        else 14
    )
    company.account_status = Company.STATUS_TRIAL
    company.subscription_expires_at = date.today() + timedelta(
        days=days,
    )
    if t:
        company.tariff = t
        company.subscription_plan = t.name
    company.save(
        update_fields=[
            "account_status",
            "subscription_expires_at",
            "tariff",
            "subscription_plan",
        ],
    )
