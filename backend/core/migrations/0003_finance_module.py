# Модуль «Финансы»: счета, статьи, журнал операций

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0002_task_new_fields"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Account",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255, verbose_name="Название")),
                ("balance", models.DecimalField(decimal_places=2, default=0, max_digits=14, verbose_name="Баланс")),
                ("currency", models.CharField(default="KZT", max_length=3, verbose_name="Валюта")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="finance_accounts", to="core.company")),
            ],
            options={
                "verbose_name": "Счёт",
                "verbose_name_plural": "Счета",
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="FinanceCategory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255, verbose_name="Название")),
                ("type", models.CharField(choices=[("income", "Доход"), ("expense", "Расход")], max_length=10, verbose_name="Тип")),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="finance_categories", to="core.company")),
            ],
            options={
                "verbose_name": "Статья",
                "verbose_name_plural": "Статьи",
                "ordering": ["type", "name"],
            },
        ),
        migrations.CreateModel(
            name="FinanceOperation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("type", models.CharField(choices=[("income", "Доход"), ("expense", "Расход"), ("transfer", "Перевод")], max_length=10, verbose_name="Тип")),
                ("amount", models.DecimalField(decimal_places=2, max_digits=14, verbose_name="Сумма")),
                ("description", models.CharField(blank=True, max_length=500, verbose_name="Описание")),
                ("contractor", models.CharField(blank=True, max_length=255, verbose_name="Контрагент")),
                ("date", models.DateField(verbose_name="Дата")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("account", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="operations", to="core.account")),
                ("account_to", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="operations_incoming", to="core.account", verbose_name="Счёт назначения")),
                ("category", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="operations", to="core.financecategory")),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="finance_operations", to="core.company")),
                ("created_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="finance_operations_created", to=settings.AUTH_USER_MODEL)),
                ("project", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="finance_operations", to="core.project")),
            ],
            options={
                "verbose_name": "Операция",
                "verbose_name_plural": "Журнал операций",
                "ordering": ["-date", "-created_at"],
            },
        ),
    ]
