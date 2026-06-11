from datetime import date

from django.db import migrations, models


def backfill_member_periods(apps, schema_editor):
    TimesheetMember = apps.get_model("core", "TimesheetMember")
    for tm in TimesheetMember.objects.all().iterator():
        changed = False
        if tm.added_at and not tm.active_from:
            tm.active_from = date(tm.added_at.year, tm.added_at.month, 1)
            changed = True
        if not tm.is_active and not tm.inactive_from:
            # Ранее удалённые глобально — скрываем с «начала времён».
            tm.inactive_from = date(1970, 1, 1)
            changed = True
        if changed:
            tm.save(update_fields=["active_from", "inactive_from"])


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0054_company_timesheet"),
    ]

    operations = [
        migrations.AddField(
            model_name="timesheetmember",
            name="active_from",
            field=models.DateField(
                blank=True,
                help_text="Первый день учёта в табеле (обычно начало месяца добавления).",
                null=True,
                verbose_name="В табеле с",
            ),
        ),
        migrations.AddField(
            model_name="timesheetmember",
            name="inactive_from",
            field=models.DateField(
                blank=True,
                help_text="Первый день исключения из табеля (удаление действует с этого месяца).",
                null=True,
                verbose_name="В табеле до",
            ),
        ),
        migrations.RunPython(backfill_member_periods, migrations.RunPython.noop),
    ]
