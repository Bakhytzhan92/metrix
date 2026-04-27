"""
HTML-страницы панели супер-администратора (/superadmin/).
"""
from __future__ import annotations

from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import ActivityLog
from .superadmin_api import dashboard_payload
from .superadmin_utils import super_admin_required

User = get_user_model()


@login_required
@require_POST
def stop_impersonation(
    request,
):
    """HTML POST: выход из режима «войти как пользователь»."""
    imp_id = request.session.pop(
        "impersonator_id",
        None,
    )
    request.session.pop(
        "impersonator_username",
        None,
    )
    if not imp_id:
        return redirect(
            "dashboard",
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
    return redirect(
        "superadmin:superadmin_panel",
    )


@login_required
@super_admin_required
def superadmin_panel(
    request,
):
    return render(
        request,
        "superadmin/panel.html",
        {
            "stats": dashboard_payload(),
        },
    )


@login_required
@super_admin_required
def superadmin_dashboard_page(
    request,
):
    return redirect(
        "superadmin:superadmin_panel",
    )


@login_required
@super_admin_required
def superadmin_companies_page(
    request,
):
    return render(
        request,
        "superadmin/companies.html",
    )


@login_required
@super_admin_required
def superadmin_users_page(
    request,
):
    return render(
        request,
        "superadmin/users.html",
    )


@login_required
@super_admin_required
def superadmin_projects_page(
    request,
):
    return render(
        request,
        "superadmin/projects.html",
    )


@login_required
@super_admin_required
def superadmin_logs_page(
    request,
):
    return render(
        request,
        "superadmin/logs.html",
    )


@login_required
@super_admin_required
def superadmin_tariffs_page(
    request,
):
    return render(
        request,
        "superadmin/tariffs.html",
    )
