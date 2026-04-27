"""
RBAC: коды прав и сопоставление URL → требуемые права.
Право view_* считается выполненным, если у роли есть edit_* для того же модуля.
"""
from __future__ import annotations

import functools

from django.http import HttpResponseForbidden, JsonResponse

# Все коды прав (для сидов и проверок)
PERMISSION_DEFINITIONS: list[tuple[str, str]] = [
    ("view_projects", "Проекты: просмотр"),
    ("edit_projects", "Проекты: редактирование"),
    ("view_estimates", "Смета: просмотр"),
    ("edit_estimates", "Смета: редактирование"),
    ("view_schedule", "График работ: просмотр"),
    ("edit_schedule", "График работ: редактирование"),
    ("view_supply", "Снабжение: просмотр"),
    ("edit_supply", "Снабжение: редактирование"),
    ("view_warehouse", "Склады: просмотр"),
    ("edit_warehouse", "Склады: редактирование"),
    ("view_finance", "Финансы: просмотр"),
    ("edit_finance", "Финансы: редактирование"),
    ("view_reports", "Отчёты: просмотр"),
    ("manage_users", "Настройки и пользователи"),
    ("view_tasks", "Задачи: просмотр"),
    ("edit_tasks", "Задачи: редактирование"),
    ("view_construction", "Стройка: просмотр"),
    ("edit_construction", "Стройка: редактирование"),
    ("view_ai", "ИИ-импорт: просмотр"),
    ("edit_ai", "ИИ-импорт: использование"),
]

# Главная: достаточно любого «входа» в модуль
HOME_ANY_OF = (
    "view_projects",
    "edit_projects",
    "view_finance",
    "edit_finance",
    "view_reports",
    "view_supply",
    "edit_supply",
    "view_warehouse",
    "edit_warehouse",
    "view_tasks",
    "edit_tasks",
    "manage_users",
)


def codes_required_for_path(path: str) -> list[str] | None:
    """
    Список кодов прав (достаточно ЛЮБОГО из списка с учётом view/edit).
    None — RBAC не применяется (страницы логина, админки и т.д.).
    Пустой список не используем.
    """
    if path.startswith("/admin/") or path.startswith("/accounts/"):
        return None
    if path.startswith("/superadmin/") or path.startswith(
        "/api/superadmin/",
    ):
        return None
    if path.startswith("/static/") or path.startswith("/media/"):
        return None

    if path in ("/", ""):
        return list(HOME_ANY_OF)

    if path.startswith("/api/"):
        if path.startswith("/api/upload-pdf/") or path.startswith("/api/document/"):
            return ["view_ai", "edit_ai"]
        return None

    if path.startswith("/projects/"):
        if "/ai/" in path:
            return ["view_ai", "edit_ai"]
        if "/estimate/" in path:
            return ["view_estimates", "edit_estimates"]
        if "/schedule/" in path:
            return ["view_schedule", "edit_schedule"]
        if "/supply/" in path:
            return ["view_supply", "edit_supply"]
        if "/finance/" in path:
            return ["view_finance", "edit_finance"]
        if "/construction/" in path:
            return ["view_construction", "edit_construction"]
        if "/warehouses/" in path:
            return ["view_warehouse", "edit_warehouse"]
        return ["view_projects", "edit_projects"]

    if path.startswith("/tasks/"):
        return ["view_tasks", "edit_tasks"]

    if path.startswith("/finance/") or path.startswith("/finances/"):
        return ["view_finance", "edit_finance"]

    if path.startswith("/supply/"):
        return ["view_supply", "edit_supply"]

    if path.startswith("/warehouses/") or path.startswith("/inventory/"):
        return ["view_warehouse", "edit_warehouse"]

    if path.startswith("/reports/"):
        return ["view_reports"]

    if path.startswith("/company/settings/") or path.startswith("/settings/"):
        return ["manage_users"]

    return None


def all_permission_codes() -> list[str]:
    return [p[0] for p in PERMISSION_DEFINITIONS]


def employee_permission_codes() -> list[str]:
    return [
        c
        for c in all_permission_codes()
        if c not in ("view_finance", "edit_finance", "view_reports", "manage_users")
    ]


def permission_codes_for_role_slug(slug: str) -> list[str]:
    """Набор кодов прав для системной роли по slug (кастомные роли — как у сотрудника)."""
    from .models import CompanyRole

    all_c = all_permission_codes()
    emp = employee_permission_codes()
    mapping: dict[str, list[str]] = {
        CompanyRole.SLUG_OWNER: all_c,
        CompanyRole.SLUG_MANAGER: all_c,
        CompanyRole.SLUG_EMPLOYEE: emp,
        CompanyRole.SLUG_PTO: [
            "view_projects",
            "edit_projects",
            "view_estimates",
            "edit_estimates",
            "view_schedule",
            "edit_schedule",
        ],
        CompanyRole.SLUG_SUPPLY: [
            "view_projects",
            "view_supply",
            "edit_supply",
            "view_warehouse",
            "edit_warehouse",
        ],
        CompanyRole.SLUG_ACCOUNTANT: ["view_finance", "edit_finance", "view_reports"],
    }
    return mapping.get((slug or "").strip(), emp)


def ensure_permission_rows_exist() -> None:
    from .models import Permission

    for code, name in PERMISSION_DEFINITIONS:
        Permission.objects.get_or_create(code=code, defaults={"name": name})


def sync_company_role_permissions(role) -> None:
    from .models import Permission

    ensure_permission_rows_exist()
    codes = permission_codes_for_role_slug(role.slug or "")
    role.permissions.set(Permission.objects.filter(code__in=codes))


def sync_all_roles_permissions_for_company(company) -> None:
    ensure_permission_rows_exist()
    for role in company.roles.all():
        sync_company_role_permissions(role)


def permission_required(code: str):
    """Декоратор view: требуется право с данным кодом (и view/edit-эквивалент)."""

    def decorator(view_func):
        @functools.wraps(view_func)
        def wrapper(request, *args, **kwargs):
            from .access_utils import get_current_company, has_permission

            company = getattr(request, "current_company", None) or get_current_company(request.user)
            if not has_permission(request.user, company, code):
                accept = (request.headers.get("Accept") or "") + (
                    request.headers.get("Content-Type") or ""
                )
                if "application/json" in accept or request.path.startswith("/api/"):
                    return JsonResponse({"ok": False, "error": "forbidden", "detail": "Нет доступа"}, status=403)
                return HttpResponseForbidden(
                    "<h1>403</h1><p>Недостаточно прав для этого действия.</p>"
                )

            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator
