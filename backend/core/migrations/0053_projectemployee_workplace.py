from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0052_timesheet_place"),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name="projectemployee",
            unique_together=set(),
        ),
        migrations.AddField(
            model_name="projectemployee",
            name="workplace",
            field=models.CharField(
                choices=[("site", "Объект"), ("office", "Офис")],
                default="site",
                max_length=16,
                verbose_name="Место учёта",
            ),
        ),
        migrations.AlterField(
            model_name="projectemployee",
            name="is_active",
            field=models.BooleanField(default=True, verbose_name="В табеле"),
        ),
        migrations.AlterUniqueTogether(
            name="projectemployee",
            unique_together={("project", "employee", "workplace")},
        ),
    ]
