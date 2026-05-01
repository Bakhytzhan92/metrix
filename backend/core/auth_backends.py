"""
Аутентификация по имени пользователя или по email (одно поле на форме входа).
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class EmailOrUsernameModelBackend(ModelBackend):
    """
    Как ModelBackend, но если пользователь с таким username не найден,
    пробуем найти учётную запись по email (без учёта регистра).
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        UserModel = get_user_model()
        if username is None:
            username = kwargs.get(UserModel.USERNAME_FIELD)
        if username is None or password is None:
            return None
        username_clean = (username or "").strip()
        if not username_clean:
            return None

        user = UserModel._default_manager.filter(
            **{UserModel.USERNAME_FIELD: username_clean}
        ).first()
        if user is None and "@" in username_clean:
            user = UserModel._default_manager.filter(
                email__iexact=username_clean,
            ).first()

        if user is None:
            UserModel().set_password(password)
            return None

        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
