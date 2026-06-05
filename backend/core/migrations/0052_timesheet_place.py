from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0051_estimate_excel_import_meta"),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name="timesheet",
            unique_together=set(),
        ),
        migrations.AddField(
            model_name="timesheet",
            name="place",
            field=models.CharField(
                choices=[("site", "Объект"), ("office", "Офис")],
                default="site",
                max_length=16,
                verbose_name="Место учёта",
            ),
        ),
        migrations.AlterUniqueTogether(
            name="timesheet",
            unique_together={("project", "year", "month", "place")},
        ),
    ]
