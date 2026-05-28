from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0037_estimateitem_subsection_header"),
    ]

    operations = [
        migrations.AlterField(
            model_name="estimateitem",
            name="schedule_status",
            field=models.CharField(
                choices=[
                    ("planned", "План"),
                    ("in_progress", "В работе"),
                    ("completed", "Завершено"),
                    ("overdue", "Просрочено"),
                    ("paused", "Пауза"),
                ],
                default="planned",
                max_length=20,
                verbose_name="График: статус",
            ),
        ),
    ]
