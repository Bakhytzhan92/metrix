"""RBAC: workflow снабжения — согласование, закупка, склад."""
from django.db import migrations

NEW_PERMS = [
    ("create_supply_request", "Снабжение: создание заявок"),
    ("approve_supply_request", "Снабжение: согласование заявок"),
    ("procure_supply", "Снабжение: закупка"),
    ("receive_supply_warehouse", "Снабжение: приём на склад"),
]

ROLE_PERMS = {
    "owner": [
        "create_supply_request",
        "approve_supply_request",
        "procure_supply",
        "receive_supply_warehouse",
    ],
    "manager": [
        "create_supply_request",
        "approve_supply_request",
        "procure_supply",
        "receive_supply_warehouse",
    ],
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
        "create_supply_request",
        "view_supply",
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
        "procure_supply",
        "receive_supply_warehouse",
    ],
    "accountant": [
        "view_finance",
        "edit_finance",
        "view_reports",
        "view_off_estimate_supply",
        "view_off_estimate_supply_cost",
        "view_supply",
    ],
}


def forwards(apps, schema_editor):
    Permission = apps.get_model("core", "Permission")
    CompanyRole = apps.get_model("core", "CompanyRole")
    for code, name in NEW_PERMS:
        Permission.objects.get_or_create(code=code, defaults={"name": name})
    all_codes = {p[0] for p in NEW_PERMS}
    perm_objs = {
        p.code: p for p in Permission.objects.filter(code__in=all_codes)
    }
    for role in CompanyRole.objects.all():
        slug = (role.slug or "").strip()
        codes = ROLE_PERMS.get(slug)
        if codes is None:
            continue
        existing = set(role.permissions.values_list("code", flat=True))
        for code in codes:
            if code in perm_objs and code not in existing:
                role.permissions.add(perm_objs[code])


def backwards(apps, schema_editor):
    Permission = apps.get_model("core", "Permission")
    Permission.objects.filter(
        code__in=[p[0] for p in NEW_PERMS]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0046_supply_workflow"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
