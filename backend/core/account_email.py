"""
Единая нормализация email и проверка занятости (без дублирования аккаунтов).
"""
from __future__ import annotations

from django.contrib.auth import get_user_model

User = get_user_model()


def normalize_email(
    email: str | None,
) -> str:
    return (email or "").strip().lower()


def is_registration_email_taken(
    email: str,
    *,
    exclude_user_id: int | None = None,
) -> bool:
    """True, если непустой email уже привязан к другому пользователю."""
    norm = normalize_email(
        email,
    )
    if not norm:
        return False
    qs = User.objects.filter(
        email__iexact=norm,
    ).exclude(
        email="",
    )
    if exclude_user_id is not None:
        qs = qs.exclude(
            pk=exclude_user_id,
        )
    return qs.exists()
