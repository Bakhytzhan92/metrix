"""
Вспомогательные функции для сессии аутентификации.
"""
from __future__ import annotations

from django.conf import settings
from django.contrib.auth import login as django_login
from django.contrib.auth.base_user import AbstractBaseUser
from django.http import HttpRequest


def login_user(request: HttpRequest, user: AbstractBaseUser) -> None:
    """
    Выполняет login() с явным backend.

    При AUTHENTICATION_BACKENDS длиной > 1 Django не знает, какой backend
    записать в сессию, если вызвать login(request, user) без `backend=`.
    """
    backend = settings.AUTHENTICATION_BACKENDS[0]
    django_login(request, user, backend=backend)
