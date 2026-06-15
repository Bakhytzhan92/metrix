import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0057_supply_order_payment_proof_doc"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ExpenseJournalEntry",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("date", models.DateField(verbose_name="Дата")),
                (
                    "amount",
                    models.DecimalField(
                        decimal_places=2,
                        default=0,
                        max_digits=16,
                        verbose_name="Сумма расхода",
                    ),
                ),
                (
                    "purpose",
                    models.CharField(
                        blank=True,
                        default="",
                        max_length=500,
                        verbose_name="Назначение платежа",
                    ),
                ),
                (
                    "payment_method",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("kaspi", "Каспи"),
                            ("cash", "Наличные"),
                            ("halyk", "Halyk"),
                            ("forte", "Forte"),
                            ("bereke", "Bereke"),
                            ("accountable", "Подотчет"),
                        ],
                        default="",
                        max_length=32,
                        verbose_name="Способ оплаты",
                    ),
                ),
                (
                    "comment",
                    models.TextField(blank=True, default="", verbose_name="Комментарий"),
                ),
                (
                    "category",
                    models.CharField(
                        choices=[
                            ("gsm", "ГСМ"),
                            ("materials", "Материалы"),
                            ("food", "Продукты"),
                            ("salary", "Зарплата"),
                            ("equipment_rent", "Аренда техники"),
                            ("parts", "Запчасти"),
                            ("tools", "Инструмент"),
                            ("telecom", "Связь"),
                            ("office", "Офис"),
                            ("business_trip", "Командировка"),
                            ("other", "Прочее"),
                        ],
                        default="other",
                        max_length=32,
                        verbose_name="Категория расхода",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "company",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="expense_journal_entries",
                        to="core.company",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="expense_journal_entries_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "finance_operation",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="expense_journal_entries",
                        to="core.financeoperation",
                        verbose_name="Операция в журнале",
                    ),
                ),
                (
                    "project",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="expense_journal_entries",
                        to="core.project",
                        verbose_name="Проект",
                    ),
                ),
                (
                    "responsible",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="expense_journal_entries",
                        to="core.employee",
                        verbose_name="Ответственное лицо",
                    ),
                ),
                (
                    "supply_order",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="expense_journal_entries",
                        to="core.supplyorder",
                        verbose_name="Заказ снабжения",
                    ),
                ),
            ],
            options={
                "verbose_name": "Запись журнала расходов",
                "verbose_name_plural": "Журнал расходов",
                "ordering": ["-date", "-id"],
            },
        ),
    ]
