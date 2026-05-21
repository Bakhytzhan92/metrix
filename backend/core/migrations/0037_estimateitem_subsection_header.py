# Generated manually for PDF import subsection banner rows

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0036_alter_stockmovement_movement_type"),
    ]

    operations = [
        migrations.AddField(
            model_name="estimateitem",
            name="is_subsection_header",
            field=models.BooleanField(
                default=False,
                verbose_name="Подзаголовок группы (строка из PDF)",
            ),
        ),
    ]
