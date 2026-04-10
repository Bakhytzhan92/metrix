# Модуль «Склады»: склады, остатки, операции

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0004_supply_module"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Warehouse",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255, verbose_name="Название")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="warehouses", to="core.company")),
                ("project", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="warehouses", to="core.project", verbose_name="Проект (приобъектный)")),
            ],
            options={
                "verbose_name": "Склад",
                "verbose_name_plural": "Склады",
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="WarehouseOperation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("operation_type", models.CharField(choices=[("incoming", "Поступление"), ("outgoing", "Списание"), ("transfer", "Перемещение")], max_length=20, verbose_name="Тип")),
                ("quantity", models.DecimalField(decimal_places=4, max_digits=14, verbose_name="Количество")),
                ("price", models.DecimalField(decimal_places=2, default=0, max_digits=14, verbose_name="Цена")),
                ("total", models.DecimalField(decimal_places=2, default=0, editable=False, max_digits=14, verbose_name="Сумма")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="warehouse_operations", to="core.company")),
                ("created_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="warehouse_operations_created", to=settings.AUTH_USER_MODEL)),
                ("from_warehouse", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="operations_out", to="core.warehouse", verbose_name="Со склада")),
                ("order", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="warehouse_operations", to="core.supplyorder", verbose_name="Заказ снабжения")),
                ("resource", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="warehouse_operations", to="core.resource")),
                ("to_warehouse", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="operations_in", to="core.warehouse", verbose_name="На склад")),
                ("warehouse", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="operations", to="core.warehouse")),
            ],
            options={
                "verbose_name": "Операция склада",
                "verbose_name_plural": "Операции склада",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="StockItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("quantity", models.DecimalField(decimal_places=4, default=0, max_digits=14, verbose_name="Количество")),
                ("price_avg", models.DecimalField(decimal_places=2, default=0, max_digits=14, verbose_name="Средняя цена")),
                ("total_sum", models.DecimalField(decimal_places=2, default=0, editable=False, max_digits=14, verbose_name="Сумма")),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("resource", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="stock_items", to="core.resource")),
                ("warehouse", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="stock_items", to="core.warehouse")),
            ],
            options={
                "verbose_name": "Остаток",
                "verbose_name_plural": "Остатки",
                "unique_together": [["warehouse", "resource"]],
            },
        ),
    ]
