from django.db import migrations, models
import django.db.models.deletion


def migrate_timesheet_to_company(apps, schema_editor):
    Timesheet = apps.get_model("core", "Timesheet")
    TimesheetEntry = apps.get_model("core", "TimesheetEntry")
    TimesheetEntryLog = apps.get_model("core", "TimesheetEntryLog")
    ProjectEmployee = apps.get_model("core", "ProjectEmployee")
    TimesheetMember = apps.get_model("core", "TimesheetMember")
    Project = apps.get_model("core", "Project")

    seen_members: set[tuple[int, int, str]] = set()
    for pe in ProjectEmployee.objects.select_related("project").iterator():
        company_id = pe.project.company_id
        key = (company_id, pe.employee_id, pe.workplace)
        if key in seen_members:
            continue
        TimesheetMember.objects.get_or_create(
            company_id=company_id,
            employee_id=pe.employee_id,
            workplace=pe.workplace,
            defaults={"is_active": pe.is_active},
        )
        seen_members.add(key)

    for ts in Timesheet.objects.exclude(project_id=None).iterator():
        company_id = Project.objects.filter(pk=ts.project_id).values_list(
            "company_id", flat=True
        ).first()
        if company_id:
            ts.company_id = company_id
            ts.save(update_fields=["company_id"])

    for ent in TimesheetEntry.objects.exclude(project_id=None).iterator():
        company_id = Project.objects.filter(pk=ent.project_id).values_list(
            "company_id", flat=True
        ).first()
        if company_id:
            ent.company_id = company_id
            ent.save(update_fields=["company_id"])

    for lg in TimesheetEntryLog.objects.exclude(project_id=None).iterator():
        company_id = Project.objects.filter(pk=lg.project_id).values_list(
            "company_id", flat=True
        ).first()
        if company_id:
            lg.company_id = company_id
            lg.save(update_fields=["company_id"])

    grouped: dict[tuple[int, int, int, str], list] = {}
    for ts in Timesheet.objects.exclude(company_id=None).iterator():
        key = (ts.company_id, ts.year, ts.month, ts.place)
        grouped.setdefault(key, []).append(ts.pk)

    for sheet_ids in grouped.values():
        if len(sheet_ids) <= 1:
            continue
        primary_id = sheet_ids[0]
        for other_id in sheet_ids[1:]:
            TimesheetEntry.objects.filter(timesheet_id=other_id).update(
                timesheet_id=primary_id
            )
            Timesheet.objects.filter(pk=other_id).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0053_projectemployee_workplace"),
    ]

    operations = [
        migrations.CreateModel(
            name="TimesheetMember",
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
                (
                    "is_active",
                    models.BooleanField(default=True, verbose_name="В табеле"),
                ),
                ("added_at", models.DateTimeField(auto_now_add=True)),
                (
                    "company",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="timesheet_members",
                        to="core.company",
                    ),
                ),
                (
                    "employee",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="timesheet_memberships",
                        to="core.employee",
                    ),
                ),
            ],
            options={
                "verbose_name": "Сотрудник в табеле",
                "verbose_name_plural": "Сотрудники в табеле",
                "ordering": ["employee__full_name", "id"],
                "unique_together": {("company", "employee", "workplace")},
            },
        ),
        migrations.AlterUniqueTogether(
            name="timesheet",
            unique_together=set(),
        ),
        migrations.AddField(
            model_name="timesheet",
            name="company",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="timesheets",
                to="core.company",
            ),
        ),
        migrations.AlterField(
            model_name="timesheet",
            name="project",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="timesheets_legacy",
                to="core.project",
            ),
        ),
        migrations.AddField(
            model_name="timesheetentry",
            name="company",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="timesheet_entries",
                to="core.company",
            ),
        ),
        migrations.AlterField(
            model_name="timesheetentry",
            name="project",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="timesheet_entries_legacy",
                to="core.project",
            ),
        ),
        migrations.AddField(
            model_name="timesheetentrylog",
            name="company",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="timesheet_logs",
                to="core.company",
            ),
        ),
        migrations.AlterField(
            model_name="timesheetentrylog",
            name="project",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="timesheet_logs_legacy",
                to="core.project",
            ),
        ),
        migrations.RunPython(migrate_timesheet_to_company, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="timesheet",
            name="company",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="timesheets",
                to="core.company",
            ),
        ),
        migrations.AlterField(
            model_name="timesheetentry",
            name="company",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="timesheet_entries",
                to="core.company",
            ),
        ),
        migrations.AlterField(
            model_name="timesheetentrylog",
            name="company",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="timesheet_logs",
                to="core.company",
            ),
        ),
        migrations.AlterUniqueTogether(
            name="timesheet",
            unique_together={("company", "year", "month", "place")},
        ),
        migrations.RemoveIndex(
            model_name="timesheetentry",
            name="core_timesh_project_cd962d_idx",
        ),
        migrations.AddIndex(
            model_name="timesheetentry",
            index=models.Index(
                fields=["company", "date"], name="core_timeshe_company_4c2f1a_idx"
            ),
        ),
    ]
