"""RBAC: согласование оплаты закупок."""
from django.db import migrations

NEW_PERM = ("approve_procurement_payment", "Снабжение: согласование закупок")

ROLE_PERMS = {
    "owner": ["approve_procurement_payment"],
    "manager": ["approve_procurement_payment"],
    "accountant": ["approve_procurement_payment"],
}


def forwards(apps, schema_editor):
    Permission = apps.get_model("core", "Permission")
    CompanyRole = apps.get_model("core", "CompanyRole")
    perm, _ = Permission.objects.get_or_create(
        code=NEW_PERM[0], defaults={"name": NEW_PERM[1]}
    )
    for role in CompanyRole.objects.all():
        slug = (role.slug or "").strip()
        codes = ROLE_PERMS.get(slug)
        if not codes:
            continue
        if NEW_PERM[0] not in set(role.permissions.values_list("code", flat=True)):
            role.permissions.add(perm)


def backwards(apps, schema_editor):
    Permission = apps.get_model("core", "Permission")
    Permission.objects.filter(code=NEW_PERM[0]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0049_supply_payment_approval"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
