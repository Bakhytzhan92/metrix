# Согласование оплаты заказов: поля, документы, журнал.
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0048_company_off_estimate_excel_header"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="supplyorder",
            name="purchase_amount",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=16,
                null=True,
                verbose_name="Сумма закупки",
            ),
        ),
        migrations.AddField(
            model_name="supplyorder",
            name="planned_delivery_date",
            field=models.DateField(
                blank=True, null=True, verbose_name="Плановая дата поставки"
            ),
        ),
        migrations.AddField(
            model_name="supplyorder",
            name="procurement_note",
            field=models.TextField(
                blank=True, default="", verbose_name="Комментарий снабженца"
            ),
        ),
        migrations.AddField(
            model_name="supplyorder",
            name="payment_rejection_reason",
            field=models.TextField(
                blank=True, default="", verbose_name="Причина отказа в оплате"
            ),
        ),
        migrations.AddField(
            model_name="supplyorder",
            name="payment_submitted_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name="Отправлено на согласование оплаты",
            ),
        ),
        migrations.AddField(
            model_name="supplyorder",
            name="payment_approved_at",
            field=models.DateTimeField(
                blank=True, null=True, verbose_name="Согласовано к оплате"
            ),
        ),
        migrations.AddField(
            model_name="supplyorder",
            name="payment_approved_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="supply_orders_payment_approved",
                to=settings.AUTH_USER_MODEL,
                verbose_name="Согласовал оплату",
            ),
        ),
        migrations.AlterField(
            model_name="supplyorder",
            name="payment_status",
            field=models.CharField(
                choices=[
                    ("draft", "Черновик"),
                    ("pending_payment_approval", "Ожидает согласования оплаты"),
                    ("payment_rejected", "Отклонено"),
                    ("awaiting_payment", "Ожидает оплаты"),
                    ("partial", "Частично оплачено"),
                    ("paid", "Оплачено"),
                ],
                default="draft",
                max_length=32,
                verbose_name="Оплата",
            ),
        ),
        migrations.AlterField(
            model_name="supplyworkflowlog",
            name="action",
            field=models.CharField(
                choices=[
                    ("created", "Создание"),
                    ("approved", "Согласование"),
                    ("rejected", "Отказ"),
                    ("procurement_started", "Передача в закупку"),
                    ("partial_purchase", "Частичная закупка"),
                    ("full_purchase", "Полная закупка"),
                    ("warehouse_transfer", "Передача на склад"),
                    ("cancelled", "Отмена"),
                    ("kp_uploaded", "Загрузка КП"),
                    ("invoice_uploaded", "Загрузка счёта"),
                    ("payment_submitted", "Отправка на согласование оплаты"),
                    ("payment_approved", "Согласование оплаты"),
                    ("payment_rejected", "Отказ в оплате"),
                    ("payment_resubmitted", "Повторная отправка на согласование"),
                    ("transferred_to_finance", "Передача в финансы"),
                ],
                max_length=32,
                verbose_name="Действие",
            ),
        ),
        migrations.CreateModel(
            name="SupplyOrderDocument",
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
                (
                    "doc_type",
                    models.CharField(
                        choices=[
                            ("kp", "Коммерческое предложение"),
                            ("invoice", "Счёт на оплату"),
                        ],
                        max_length=16,
                        verbose_name="Тип",
                    ),
                ),
                (
                    "file",
                    models.FileField(
                        upload_to="supply_orders/documents/%Y/%m/", verbose_name="Файл"
                    ),
                ),
                ("version", models.PositiveIntegerField(default=1, verbose_name="Версия")),
                ("uploaded_at", models.DateTimeField(auto_now_add=True)),
                (
                    "order",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="documents",
                        to="core.supplyorder",
                    ),
                ),
                (
                    "uploaded_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="supply_order_documents_uploaded",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Документ заказа",
                "verbose_name_plural": "Документы заказа",
                "ordering": ["doc_type", "-version", "-id"],
            },
        ),
        migrations.AddConstraint(
            model_name="supplyorderdocument",
            constraint=models.UniqueConstraint(
                fields=("order", "doc_type", "version"),
                name="uniq_supply_order_doc_version",
            ),
        ),
    ]
