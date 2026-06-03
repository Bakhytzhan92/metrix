from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0050_supply_payment_approval_rbac"),
    ]

    operations = [
        migrations.AddField(
            model_name="estimatesection",
            name="header_style",
            field=models.CharField(
                blank=True,
                choices=[
                    ("", "Обычный"),
                    ("red", "Красный (как в Excel)"),
                    ("gold", "Золотой (как в Excel)"),
                    ("bordeaux", "Бордовый (как в Excel)"),
                ],
                default="",
                max_length=16,
                verbose_name="Стиль заголовка (импорт Excel)",
            ),
        ),
        migrations.AlterField(
            model_name="estimateitem",
            name="unit",
            field=models.CharField(
                default="шт", max_length=128, verbose_name="Ед. изм."
            ),
        ),
    ]
