# RBAC for off-estimate supply requests

from django.db import migrations


OFF_ESTIMATE_PERMISSIONS = [
    ("view_off_estimate_supply", "Заявки вне сметы: просмотр"),
    ("edit_off_estimate_supply", "Заявки вне сметы: редактирование"),
    ("view_off_estimate_supply_cost", "Заявки вне сметы: просмотр стоимости"),
]


def sync_off_estimate_rbac(apps, schema_editor):
    Permission = apps.get_model("core", "Permission")
    CompanyRole = apps.get_model("core", "CompanyRole")

    for code, name in OFF_ESTIMATE_PERMISSIONS:
        Permission.objects.get_or_create(code=code, defaults={"name": name})

    perm_by_code = {p.code: p for p in Permission.objects.all()}
    all_codes = list(perm_by_code.keys())
    employee_codes = [
        c
        for c in all_codes
        if c
        not in (
            "view_finance",
            "edit_finance",
            "view_reports",
            "manage_users",
            "view_off_estimate_supply",
            "edit_off_estimate_supply",
            "view_off_estimate_supply_cost",
        )
    ]
    slug_to_codes = {
        "owner": all_codes,
        "manager": all_codes,
        "employee": employee_codes,
        "pto": [
            "view_projects",
            "edit_projects",
            "view_estimates",
            "edit_estimates",
            "view_schedule",
            "edit_schedule",
            "view_timesheet",
            "edit_timesheet",
            "view_off_estimate_supply",
        ],
        "supply": [
            "view_projects",
            "view_supply",
            "edit_supply",
            "view_off_estimate_supply",
            "edit_off_estimate_supply",
            "view_off_estimate_supply_cost",
            "view_warehouse",
            "edit_warehouse",
        ],
        "accountant": [
            "view_finance",
            "edit_finance",
            "view_reports",
            "view_off_estimate_supply",
            "view_off_estimate_supply_cost",
        ],
    }

    for role in CompanyRole.objects.all():
        slug = (role.slug or "").strip()
        codes = slug_to_codes.get(slug, employee_codes)
        role.permissions.set([perm_by_code[c] for c in codes if c in perm_by_code])


def reverse_off_estimate_rbac(apps, schema_editor):
    Permission = apps.get_model("core", "Permission")
    Permission.objects.filter(
        code__in=[c for c, _ in OFF_ESTIMATE_PERMISSIONS]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0041_off_estimate_supply_module"),
    ]

    operations = [
        migrations.RunPython(sync_off_estimate_rbac, reverse_off_estimate_rbac),
    ]
