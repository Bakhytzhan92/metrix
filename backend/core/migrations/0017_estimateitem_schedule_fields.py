# Generated manually for EstimateItem schedule fields

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0016_project_schedule_phase"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="estimateitem",
            name="schedule_start",
            field=models.DateField(
                blank=True, null=True, verbose_name="График: начало"
            ),
        ),
        migrations.AddField(
            model_name="estimateitem",
            name="schedule_end",
            field=models.DateField(
                blank=True, null=True, verbose_name="График: окончание"
            ),
        ),
        migrations.AddField(
            model_name="estimateitem",
            name="schedule_status",
            field=models.CharField(
                choices=[
                    ("planned", "План"),
                    ("in_progress", "В работе"),
                    ("completed", "Завершено"),
                ],
                default="planned",
                max_length=20,
                verbose_name="График: статус",
            ),
        ),
        migrations.AddField(
            model_name="estimateitem",
            name="schedule_assignee",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="estimate_items_schedule_assigned",
                to=settings.AUTH_USER_MODEL,
                verbose_name="График: ответственный",
            ),
        ),
        migrations.AddField(
            model_name="estimateitem",
            name="schedule_predecessor",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="schedule_dependents",
                to="core.estimateitem",
                verbose_name="График: предыдущая позиция",
            ),
        ),
    ]
