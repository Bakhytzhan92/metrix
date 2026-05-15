# Generated manually for project materials module

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0028_inventory_erp_stage1"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="material",
            name="description",
            field=models.TextField(blank=True, verbose_name="Описание"),
        ),
        migrations.AddField(
            model_name="material",
            name="supplier",
            field=models.CharField(blank=True, max_length=255, verbose_name="Поставщик"),
        ),
        migrations.AddField(
            model_name="stockmovement",
            name="schedule_phase",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="material_movements",
                to="core.projectschedulephase",
                verbose_name="Этап работ",
            ),
        ),
        migrations.AddField(
            model_name="stockmovement",
            name="supplier",
            field=models.CharField(blank=True, max_length=255, verbose_name="Поставщик"),
        ),
        migrations.AddField(
            model_name="stockmovement",
            name="user",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="stock_movements_recorded",
                to=settings.AUTH_USER_MODEL,
                verbose_name="Пользователь",
            ),
        ),
        migrations.AddField(
            model_name="stockmovement",
            name="writeoff_reason",
            field=models.CharField(
                blank=True,
                choices=[
                    ("used", "Использовано"),
                    ("defect", "Брак"),
                    ("loss", "Потеря"),
                    ("damage", "Повреждение"),
                ],
                max_length=20,
                verbose_name="Причина списания",
            ),
        ),
    ]
