from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from core.models import UserProfile


class Command(BaseCommand):
    help = (
        "Снять флаг суперадмина SaaS с одного пользователя и выдать другому "
        "(UserProfile.is_super_admin)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "grant_username",
            help="Логин, которому выставить is_super_admin=True",
        )
        parser.add_argument(
            "revoke_username",
            help="Логин, у которого выставить is_super_admin=False",
        )

    def handle(self, *args, **options):
        grant_name = options["grant_username"]
        revoke_name = options["revoke_username"]
        User = get_user_model()

        if grant_name == revoke_name:
            raise CommandError("Логины grant и revoke должны различаться.")

        try:
            u_grant = User.objects.get(username=grant_name)
            u_revoke = User.objects.get(username=revoke_name)
        except User.DoesNotExist as e:
            raise CommandError(f"Пользователь не найден: {e}") from e

        p_grant, _ = UserProfile.objects.get_or_create(user=u_grant)
        p_grant.is_super_admin = True
        p_grant.save(update_fields=["is_super_admin"])

        p_revoke, _ = UserProfile.objects.get_or_create(user=u_revoke)
        p_revoke.is_super_admin = False
        p_revoke.save(update_fields=["is_super_admin"])

        self.stdout.write(
            self.style.SUCCESS(
                f"OK: {grant_name} → super_admin=True; "
                f"{revoke_name} → super_admin=False"
            )
        )
        active = list(
            UserProfile.objects.filter(is_super_admin=True).values_list(
                "user__username",
                flat=True,
            )
        )
        self.stdout.write(f"Сейчас суперадмины SaaS: {active}")
