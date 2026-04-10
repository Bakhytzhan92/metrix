# Backfill: системные роли и CompanyUser для владельцев существующих компаний

from django.db import migrations


def backfill_company_roles(apps, schema_editor):
    Company = apps.get_model("core", "Company")
    CompanyRole = apps.get_model("core", "CompanyRole")
    CompanyUser = apps.get_model("core", "CompanyUser")
    roles_data = [
        ("owner", "Владелец компании", "Полный доступ ко всем модулям"),
        ("manager", "Руководитель (только просмотр)", "Доступ на чтение ко всем разделам без редактирования"),
        ("employee", "Сотрудник", "Доступ ко всем модулям кроме: Отчёты, Финансы, Настройки"),
    ]
    for company in Company.objects.all():
        for slug, name, description in roles_data:
            CompanyRole.objects.get_or_create(
                company=company,
                slug=slug,
                defaults={"name": name, "description": description, "is_system": True},
            )
        owner_role = CompanyRole.objects.get(company=company, slug="owner")
        CompanyUser.objects.get_or_create(
            user_id=company.owner_id,
            company=company,
            defaults={"role_id": owner_role.id, "is_active": True},
        )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0007_access_roles"),
    ]

    operations = [
        migrations.RunPython(backfill_company_roles, noop),
    ]
