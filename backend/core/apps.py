from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"
    verbose_name = "Metrix SaaS"

    def ready(
        self,
    ) -> None:
        from django.contrib.auth.models import User

        from . import signals  # noqa: F401
        from .models import UserProfile

        def _is_super_admin(
            self,
        ) -> bool:
            if not self.is_authenticated:
                return False
            try:
                return bool(
                    self.saas_profile.is_super_admin,
                )
            except UserProfile.DoesNotExist:
                return False

        User.add_to_class(
            "is_super_admin",
            property(
                _is_super_admin,
            ),
        )

