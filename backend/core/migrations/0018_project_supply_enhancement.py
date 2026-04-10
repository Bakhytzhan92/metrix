# SupplyRequest: смета, сроки, статусы Gectaro; SupplyOrder: проект, оплата, финансы

import django.db.models.deletion
from decimal import Decimal

from django.db import migrations, models


def migrate_supply_request_statuses(apps, schema_editor):
    SupplyRequest = apps.get_model("core", "SupplyRequest")
    MAP = {
        "approved": "pending",
        "ordered": "in_progress",
        "delivered": "purchased",
    }
    for r in SupplyRequest.objects.all().only("id", "status"):
        nv = MAP.get(r.status)
        if nv:
            r.status = nv
            r.save(update_fields=["status"])


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0017_estimateitem_schedule_fields"),
    ]

    operations = [
        migrations.AlterField(
            model_name="resource",
            name="type",
            field=models.CharField(
                choices=[
                    ("material", "Материал"),
                    ("labor", "Труд / люди"),
                    ("service", "Услуга"),
                    ("equipment", "Механизмы"),
                ],
                default="material",
                max_length=20,
                verbose_name="Тип",
            ),
        ),
        migrations.AddField(
            model_name="supplyrequest",
            name="delivery_date",
            field=models.DateField(
                blank=True, null=True, verbose_name="Срок доставки"
            ),
        ),
        migrations.AddField(
            model_name="supplyrequest",
            name="estimate_item",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="supply_requests",
                to="core.estimateitem",
                verbose_name="Позиция сметы",
            ),
        ),
        migrations.AddField(
            model_name="supplyrequest",
            name="quantity_received",
            field=models.DecimalField(
                decimal_places=4,
                default=Decimal("0"),
                max_digits=14,
                verbose_name="Закуплено (факт, кол-во)",
            ),
        ),
        migrations.AddField(
            model_name="supplyrequest",
            name="supplier_name",
            field=models.CharField(
                blank=True, max_length=255, verbose_name="Поставщик (заявка)"
            ),
        ),
        migrations.AlterField(
            model_name="supplyrequest",
            name="price_plan",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0"),
                max_digits=14,
                verbose_name="Цена за ед., план",
            ),
        ),
        migrations.AlterField(
            model_name="supplyrequest",
            name="status",
            field=models.CharField(
                choices=[
                    ("draft", "Черновик"),
                    ("pending", "Ожидает закупки"),
                    ("in_progress", "В закупке"),
                    ("partial", "Частично закуплено"),
                    ("purchased", "Закуплено"),
                    ("cancelled", "Отменена"),
                ],
                default="draft",
                max_length=20,
                verbose_name="Статус",
            ),
        ),
        migrations.RunPython(
            migrate_supply_request_statuses, migrations.RunPython.noop
        ),
        migrations.AddField(
            model_name="supplyorder",
            name="finance_operation",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="supply_orders",
                to="core.financeoperation",
                verbose_name="Операция в финансах",
            ),
        ),
        migrations.AddField(
            model_name="supplyorder",
            name="payment_status",
            field=models.CharField(
                choices=[
                    ("unpaid", "Не оплачен"),
                    ("partial", "Частично оплачен"),
                    ("paid", "Оплачен"),
                ],
                default="unpaid",
                max_length=20,
                verbose_name="Оплата",
            ),
        ),
        migrations.AddField(
            model_name="supplyorder",
            name="project",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="supply_orders",
                to="core.project",
                verbose_name="Проект",
            ),
        ),
        migrations.AddField(
            model_name="supplyorder",
            name="total_amount",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0"),
                editable=False,
                max_digits=16,
                verbose_name="Сумма заказа",
            ),
        ),
    ]
