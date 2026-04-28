"""
JSON API для панели супер-администратора (/api/superadmin/...).
"""
from __future__ import annotations

import secrets

from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, ProtectedError, Q
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from .models import (
    ActivityLog,
    Company,
    CompanyUser,
    Project,
    Tariff,
    UserProfile,
)
from .superadmin_utils import (
    log_saas_activity,
    parse_json_body,
    super_admin_required,
)
from .subscription_limits import (
    refresh_account_status_from_dates,
    resolve_company_tariff,
)


User = get_user_model()


def _json_ok(
    **data,
):
    return JsonResponse(
        {
            "ok": True,
            **data,
        },
    )


def dashboard_payload():
    total_companies = Company.objects.count()
    active_companies = Company.objects.filter(
        is_active=True,
        account_status__in=[
            Company.STATUS_ACTIVE,
            Company.STATUS_TRIAL,
        ],
    ).count()
    total_users = User.objects.filter(
        is_active=True,
    ).count()
    total_projects = Project.objects.count()
    return {
        "total_companies": total_companies,
        "active_companies": active_companies,
        "total_users": total_users,
        "total_projects": total_projects,
    }


@require_GET
@super_admin_required
def api_dashboard(
    request,
):
    return _json_ok(
        **dashboard_payload(),
    )


@require_GET
@super_admin_required
def api_companies(
    request,
):
    qs = (
        Company.objects.select_related(
            "owner",
            "tariff",
        )
        .annotate(
            project_count=Count(
                "projects",
            ),
            user_count=Count(
                "company_users",
                filter=Q(
                    company_users__is_active=True,
                ),
            ),
        )
        .order_by(
            "-created_at",
        )
    )
    rows = []
    for c in qs:
        refresh_account_status_from_dates(
            c,
        )
        rows.append(
            {
                "id": c.id,
                "name": c.name,
                "contact_email": c.contact_email or "",
                "owner_id": c.owner_id,
                "owner_username": c.owner.get_username(),
                "owner_email": getattr(
                    c.owner,
                    "email",
                    "",
                )
                or "",
                "tariff": c.display_tariff_name,
                "tariff_id": c.tariff_id,
                "subscription_plan": c.subscription_plan,
                "subscription_expires_at": (
                    c.subscription_expires_at.isoformat()
                    if c.subscription_expires_at
                    else None
                ),
                "is_active": c.is_active,
                "account_status": c.account_status,
                "created_at": c.created_at.isoformat(),
                "project_count": c.project_count,
                "user_count": c.user_count,
            },
        )
    return _json_ok(
        companies=rows,
    )


@require_POST
@super_admin_required
def api_company_block(
    request,
    pk: int,
):
    c = get_object_or_404(
        Company,
        pk=pk,
    )
    c.is_active = False
    c.account_status = Company.STATUS_BLOCKED
    c.save(
        update_fields=[
            "is_active",
            "account_status",
        ],
    )
    log_saas_activity(
        request,
        f"Блокировка компании «{c.name}»",
        "company",
        str(
            c.pk,
        ),
    )
    return _json_ok(
        company_id=c.id,
    )


@require_POST
@super_admin_required
def api_company_activate(
    request,
    pk: int,
):
    c = get_object_or_404(
        Company,
        pk=pk,
    )
    c.is_active = True
    if c.account_status == Company.STATUS_BLOCKED:
        c.account_status = Company.STATUS_ACTIVE
    c.save(
        update_fields=[
            "is_active",
            "account_status",
        ],
    )
    log_saas_activity(
        request,
        f"Активация компании «{c.name}»",
        "company",
        str(
            c.pk,
        ),
    )
    return _json_ok(
        company_id=c.id,
    )


@require_POST
@super_admin_required
def api_company_delete(
    request,
    pk: int,
):
    """
    Полное удаление аккаунта компании (тенанта): проекты, сметы, пользователи
    компании и связанные данные удаляются каскадно. Пользователь-владелец в
    системе остаётся (можно удалить отдельно из админки при необходимости).
    """
    c = get_object_or_404(
        Company,
        pk=pk,
    )
    label = c.name
    cid = c.pk
    log_saas_activity(
        request,
        f"Удаление компании «{label}» (полное)",
        "company",
        str(
            cid,
        ),
    )
    try:
        with transaction.atomic():
            c.delete()
    except ProtectedError as exc:
        return JsonResponse(
            {
                "ok": False,
                "error": "Нельзя удалить: есть связанные записи с защитой от удаления. "
                + str(
                    exc,
                )[:500],
            },
            status=409,
        )
    except Exception as exc:
        return JsonResponse(
            {
                "ok": False,
                "error": str(
                    exc,
                )[:500],
            },
            status=500,
        )
    return _json_ok(
        deleted_id=cid,
        deleted_name=label,
    )


@require_POST
@super_admin_required
def api_company_change_tariff(
    request,
    pk: int,
):
    c = get_object_or_404(
        Company,
        pk=pk,
    )
    body = parse_json_body(
        request,
    )
    tid = body.get(
        "tariff_id",
    )
    if tid is None:
        return JsonResponse(
            {
                "ok": False,
                "error": "tariff_id обязателен",
            },
            status=400,
        )
    t = get_object_or_404(
        Tariff,
        pk=int(
            tid,
        ),
    )
    c.tariff = t
    c.subscription_plan = t.name
    c.save(
        update_fields=[
            "tariff",
            "subscription_plan",
        ],
    )
    log_saas_activity(
        request,
        f"Смена тарифа компании «{c.name}» на «{t.name}»",
        "company",
        str(
            c.pk,
        ),
        meta={
            "tariff_id": t.id,
        },
    )
    return _json_ok(
        company_id=c.id,
        tariff_id=t.id,
    )


@require_GET
@super_admin_required
def api_users(
    request,
):
    company_id = request.GET.get(
        "company",
    )
    qs = User.objects.all().order_by(
        "-date_joined",
    )
    if company_id:
        qs = qs.filter(
            company_users__company_id=int(
                company_id,
            ),
        ).distinct()
    rows = []
    for u in qs[:2000]:
        cu = (
            CompanyUser.objects.filter(
                user=u,
                is_active=True,
            )
            .select_related(
                "company",
                "role",
            )
            .first()
        )
        rows.append(
            {
                "id": u.id,
                "username": u.get_username(),
                "email": u.email or "",
                "is_active": u.is_active,
                "is_staff": u.is_staff,
                "date_joined": u.date_joined.isoformat(),
                "company_id": cu.company_id if cu else None,
                "company_name": cu.company.name if cu else "",
                "role": (
                    (cu.role.name if cu and cu.role_id else "")
                    or ""
                ),
            },
        )
    return _json_ok(
        users=rows,
    )


@require_POST
@super_admin_required
def api_user_reset_password(
    request,
    pk: int,
):
    u = get_object_or_404(
        User,
        pk=pk,
    )
    new_pw = secrets.token_urlsafe(
        16,
    )
    u.set_password(
        new_pw,
    )
    u.save(
        update_fields=["password"],
    )
    log_saas_activity(
        request,
        f"Сброс пароля пользователя {u.get_username()}",
        "user",
        str(
            u.pk,
        ),
    )
    return _json_ok(
        user_id=u.id,
        temporary_password=new_pw,
    )


@require_POST
@super_admin_required
def api_user_delete(
    request,
    pk: int,
):
    """
    Удаление учётной записи пользователя (сессии, членства, профиль SaaS и т.д.
    каскадно). Не удаляет владельца компаний — сначала компании или смена владельца.
    """
    if int(
        pk,
    ) == int(
        request.user.pk,
    ):
        return JsonResponse(
            {
                "ok": False,
                "error": "Нельзя удалить свою текущую учётную запись.",
            },
            status=400,
        )
    u = get_object_or_404(
        User,
        pk=pk,
    )
    if u.owned_companies.exists():
        return JsonResponse(
            {
                "ok": False,
                "error": "Пользователь — владелец одной или нескольких компаний. "
                "Сначала удалите эти компании в разделе «Компании» или назначьте другого владельца.",
            },
            status=409,
        )
    if UserProfile.objects.filter(
        user=u,
        is_super_admin=True,
    ).exists():
        other = (
            UserProfile.objects.filter(
                is_super_admin=True,
            )
            .exclude(
                user_id=u.pk,
            )
            .count()
        )
        if other < 1:
            return JsonResponse(
                {
                    "ok": False,
                    "error": "Нельзя удалить последнего супер-администратора платформы.",
                },
                status=400,
            )
    label = u.get_username()
    uid = u.pk
    log_saas_activity(
        request,
        f"Удаление пользователя «{label}»",
        "user",
        str(
            uid,
        ),
    )
    try:
        with transaction.atomic():
            u.delete()
    except ProtectedError as exc:
        return JsonResponse(
            {
                "ok": False,
                "error": "Нельзя удалить: "
                + str(
                    exc,
                )[:500],
            },
            status=409,
        )
    except Exception as exc:
        return JsonResponse(
            {
                "ok": False,
                "error": str(
                    exc,
                )[:500],
            },
            status=500,
        )
    return _json_ok(
        deleted_id=uid,
        deleted_username=label,
    )


@require_GET
@super_admin_required
def api_projects(
    request,
):
    company_id = request.GET.get(
        "company",
    )
    qs = Project.objects.select_related(
        "company",
    ).order_by(
        "-created_at",
    )
    if company_id:
        qs = qs.filter(
            company_id=int(
                company_id,
            ),
        )
    rows = [
        {
            "id": p.id,
            "name": p.name,
            "company_id": p.company_id,
            "company_name": p.company.name,
            "status": p.status,
            "created_at": p.created_at.isoformat(),
        }
        for p in qs[:3000]
    ]
    return _json_ok(
        projects=rows,
    )


@require_GET
@super_admin_required
def api_logs(
    request,
):
    qs = ActivityLog.objects.select_related(
        "user",
    ).order_by(
        "-created_at",
    )[:500]
    rows = [
        {
            "id": log.id,
            "user": log.user.get_username(),
            "user_id": log.user_id,
            "action": log.action,
            "entity": log.entity,
            "entity_id": log.entity_id,
            "created_at": log.created_at.isoformat(),
        }
        for log in qs
    ]
    return _json_ok(
        logs=rows,
    )


@require_GET
@super_admin_required
def api_tariffs(
    request,
):
    rows = [
        {
            "id": t.id,
            "name": t.name,
            "max_projects": t.max_projects,
            "max_users": t.max_users,
            "trial_days": t.trial_days,
        }
        for t in Tariff.objects.order_by(
            "name",
        )
    ]
    return _json_ok(
        tariffs=rows,
    )


@require_POST
@super_admin_required
def api_login_as_user(
    request,
    user_id: int,
):
    admin = request.user
    target = get_object_or_404(
        User,
        pk=user_id,
    )
    ActivityLog.objects.create(
        user=admin,
        action=f"Имперсонация: вход как {target.get_username()}",
        entity="user",
        entity_id=str(
            target.pk,
        ),
    )
    request.session[
        "impersonator_id"
    ] = admin.pk
    request.session[
        "impersonator_username"
    ] = admin.get_username()
    login(
        request,
        target,
    )
    return _json_ok(
        redirect="/",
    )


@require_POST
@login_required
def api_stop_impersonation(
    request,
):
    imp_id = request.session.pop(
        "impersonator_id",
        None,
    )
    request.session.pop(
        "impersonator_username",
        None,
    )
    if not imp_id:
        return JsonResponse(
            {
                "ok": False,
                "error": "Режим имперсонации не активен",
            },
            status=400,
        )
    admin = get_object_or_404(
        User,
        pk=imp_id,
    )
    ActivityLog.objects.create(
        user=admin,
        action="Выход из режима имперсонации",
        entity="session",
        entity_id="",
    )
    login(
        request,
        admin,
    )
    accept = request.headers.get(
        "Accept",
        "",
    )
    if "application/json" in accept:
        return _json_ok(
            redirect="/superadmin/",
        )
    return HttpResponseRedirect(
        reverse(
            "superadmin:superadmin_panel",
        ),
    )
