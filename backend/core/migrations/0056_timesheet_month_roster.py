from datetime import date, timedelta

from django.db import migrations, models
import django.db.models.deletion


def _iter_months(start: date, end: date):
    y, m = start.year, start.month
    end_y, end_m = end.year, end.month
    while (y, m) <= (end_y, end_m):
        yield y, m
        m += 1
        if m > 12:
            m = 1
            y += 1


def populate_month_rosters(apps, schema_editor):
    TimesheetMember = apps.get_model("core", "TimesheetMember")
    TimesheetEntry = apps.get_model("core", "TimesheetEntry")
    TimesheetMonthRoster = apps.get_model("core", "TimesheetMonthRoster")
    Timesheet = apps.get_model("core", "Timesheet")

    for ent in TimesheetEntry.objects.select_related("timesheet").iterator():
        place = ent.timesheet.place
        TimesheetMonthRoster.objects.get_or_create(
            company_id=ent.company_id,
            employee_id=ent.employee_id,
            workplace=place,
            year=ent.date.year,
            month=ent.date.month,
        )

    today = date.today()
    legacy_cutoff = date(1970, 1, 2)
    for tm in TimesheetMember.objects.all().iterator():
        if getattr(tm, "inactive_from", None) and tm.inactive_from <= legacy_cutoff:
            continue
        if getattr(tm, "active_from", None):
            start = tm.active_from
        elif tm.added_at:
            start = date(tm.added_at.year, tm.added_at.month, 1)
        else:
            start = date(today.year, today.month, 1)

        if getattr(tm, "inactive_from", None) and tm.inactive_from > legacy_cutoff:
            prev = tm.inactive_from - timedelta(days=1)
            end = date(prev.year, prev.month, 1)
        elif tm.is_active:
            end = date(today.year, today.month, 1)
        else:
            end = start

        if end < start:
            continue
        for y, m in _iter_months(start, end):
            TimesheetMonthRoster.objects.get_or_create(
                company_id=tm.company_id,
                employee_id=tm.employee_id,
                workplace=tm.workplace,
                year=y,
                month=m,
            )


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0055_timesheet_member_periods"),
    ]

    operations = [
        migrations.CreateModel(
            name="TimesheetMonthRoster",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "workplace",
                    models.CharField(
                        choices=[("site", "Объект"), ("office", "Офис")],
                        default="site",
                        max_length=16,
                        verbose_name="Место учёта",
                    ),
                ),
                ("year", models.PositiveSmallIntegerField(verbose_name="Год")),
                ("month", models.PositiveSmallIntegerField(verbose_name="Месяц")),
                (
                    "company",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="timesheet_month_rosters",
                        to="core.company",
                    ),
                ),
                (
                    "employee",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="timesheet_month_rosters",
                        to="core.employee",
                    ),
                ),
            ],
            options={
                "verbose_name": "Состав табеля за месяц",
                "verbose_name_plural": "Состав табеля по месяцам",
                "ordering": ["year", "month", "employee__full_name"],
                "unique_together": {("company", "employee", "workplace", "year", "month")},
            },
        ),
        migrations.RunPython(populate_month_rosters, migrations.RunPython.noop),
    ]
