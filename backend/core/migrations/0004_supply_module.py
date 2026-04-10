# Модуль «Снабжение»: ресурсы, заявки, заказы

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0003_finance_module"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Resource",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255, verbose_name="Название")),
                ("type", models.CharField(choices=[("material", "Материал"), ("service", "Услуга"), ("equipment", "Оборудование")], default="material", max_length=20, verbose_name="Тип")),
                ("unit", models.CharField(default="шт.", max_length=50, verbose_name="Единица")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="supply_resources", to="core.company")),
            ],
            options={
                "verbose_name": "Ресурс",
                "verbose_name_plural": "Ресурсы",
                "ordering": ["type", "name"],
            },
        ),
        migrations.CreateModel(
            name="SupplyOrder",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("supplier", models.CharField(max_length=255, verbose_name="Поставщик")),
                ("status", models.CharField(choices=[("new", "Новый"), ("paid", "Оплачен"), ("delivered", "Поставлен"), ("closed", "Закрыт")], default="new", max_length=20, verbose_name="Статус")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="supply_orders", to="core.company")),
            ],
            options={
                "verbose_name": "Заказ",
                "verbose_name_plural": "Заказы",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="SupplyRequest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("required_date", models.DateField(verbose_name="Потребуется")),
                ("quantity", models.DecimalField(decimal_places=4, default=0, max_digits=14, verbose_name="Количество")),
                ("price_plan", models.DecimalField(decimal_places=2, default=0, max_digits=14, verbose_name="Цена, план")),
                ("total_plan", models.DecimalField(decimal_places=2, default=0, editable=False, max_digits=14, verbose_name="План, сумма")),
                ("status", models.CharField(choices=[("draft", "Черновик"), ("approved", "Согласована"), ("ordered", "В заказе"), ("delivered", "Поставлено"), ("cancelled", "Отменена")], default="draft", max_length=20, verbose_name="Статус")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="supply_requests", to="core.company")),
                ("created_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="supply_requests_created", to=settings.AUTH_USER_MODEL)),
                ("project", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="supply_requests", to="core.project")),
                ("resource", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="requests", to="core.resource")),
            ],
            options={
                "verbose_name": "Заявка",
                "verbose_name_plural": "Заявки",
                "ordering": ["-required_date", "-created_at"],
            },
        ),
        migrations.CreateModel(
            name="SupplyOrderItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("quantity", models.DecimalField(decimal_places=4, default=0, max_digits=14, verbose_name="Количество")),
                ("price_fact", models.DecimalField(decimal_places=2, default=0, max_digits=14, verbose_name="Цена, факт")),
                ("total_fact", models.DecimalField(decimal_places=2, default=0, editable=False, max_digits=14, verbose_name="Факт, сумма")),
                ("order", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="items", to="core.supplyorder")),
                ("request", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="order_item", to="core.supplyrequest")),
            ],
            options={
                "verbose_name": "Позиция заказа",
                "verbose_name_plural": "Позиции заказа",
            },
        ),
    ]
