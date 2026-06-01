# Заявки вне сметы: шапка + позиции

import django.db.models.deletion
from django.db import migrations, models


def migrate_requests_to_items(apps, schema_editor):
    Request = apps.get_model("core", "OffEstimateSupplyRequest")
    Item = apps.get_model("core", "OffEstimateSupplyRequestItem")
    for req in Request.objects.all():
        Item.objects.create(
            request_id=req.pk,
            sort_order=0,
            material_name=getattr(req, "material_name", "") or "—",
            unit=getattr(req, "unit", "") or "шт",
            quantity=getattr(req, "quantity", 0) or 0,
            price_plan=getattr(req, "price_plan", None),
            total_plan=getattr(req, "total_plan", 0) or 0,
            quantity_purchased=getattr(req, "quantity_purchased", 0) or 0,
            total_purchased=getattr(req, "total_purchased", 0) or 0,
            warehouse_received=getattr(req, "warehouse_received", False),
            warehouse_received_at=getattr(req, "warehouse_received_at", None),
            material_id=getattr(req, "material_id", None),
            warehouse_id=getattr(req, "warehouse_id", None),
        )


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0043_off_estimate_employee_rbac_fix"),
    ]

    operations = [
        migrations.CreateModel(
            name="OffEstimateSupplyRequestItem",
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
                    "sort_order",
                    models.PositiveSmallIntegerField(default=0, verbose_name="Порядок"),
                ),
                (
                    "material_name",
                    models.CharField(
                        max_length=255, verbose_name="Наименование материала"
                    ),
                ),
                (
                    "unit",
                    models.CharField(
                        default="шт", max_length=50, verbose_name="Ед. изм."
                    ),
                ),
                (
                    "quantity",
                    models.DecimalField(
                        decimal_places=4,
                        default=0,
                        max_digits=14,
                        verbose_name="Количество",
                    ),
                ),
                (
                    "price_plan",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=14,
                        null=True,
                        verbose_name="Плановая цена",
                    ),
                ),
                (
                    "total_plan",
                    models.DecimalField(
                        decimal_places=2,
                        default=0,
                        editable=False,
                        max_digits=14,
                        verbose_name="Плановая сумма",
                    ),
                ),
                (
                    "quantity_purchased",
                    models.DecimalField(
                        decimal_places=4,
                        default=0,
                        max_digits=14,
                        verbose_name="Фактически закуплено",
                    ),
                ),
                (
                    "total_purchased",
                    models.DecimalField(
                        decimal_places=2,
                        default=0,
                        max_digits=14,
                        verbose_name="Сумма закупки",
                    ),
                ),
                (
                    "warehouse_received",
                    models.BooleanField(default=False, verbose_name="Принято на склад"),
                ),
                ("warehouse_received_at", models.DateTimeField(blank=True, null=True)),
                (
                    "material",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="off_estimate_supply_items",
                        to="core.material",
                        verbose_name="Материал на складе",
                    ),
                ),
                (
                    "request",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="items",
                        to="core.offestimatesupplyrequest",
                    ),
                ),
                (
                    "warehouse",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="off_estimate_supply_items",
                        to="core.warehouse",
                        verbose_name="Склад поступления",
                    ),
                ),
            ],
            options={
                "verbose_name": "Позиция заявки вне сметы",
                "verbose_name_plural": "Позиции заявок вне сметы",
                "ordering": ["sort_order", "id"],
            },
        ),
        migrations.RunPython(migrate_requests_to_items, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="offestimatesupplyrequest",
            name="material",
        ),
        migrations.RemoveField(
            model_name="offestimatesupplyrequest",
            name="material_name",
        ),
        migrations.RemoveField(
            model_name="offestimatesupplyrequest",
            name="price_plan",
        ),
        migrations.RemoveField(
            model_name="offestimatesupplyrequest",
            name="quantity",
        ),
        migrations.RemoveField(
            model_name="offestimatesupplyrequest",
            name="quantity_purchased",
        ),
        migrations.RemoveField(
            model_name="offestimatesupplyrequest",
            name="unit",
        ),
        migrations.RemoveField(
            model_name="offestimatesupplyrequest",
            name="warehouse",
        ),
        migrations.RemoveField(
            model_name="offestimatesupplyrequest",
            name="warehouse_received",
        ),
        migrations.RemoveField(
            model_name="offestimatesupplyrequest",
            name="warehouse_received_at",
        ),
        migrations.AlterField(
            model_name="offestimatesupplyrequest",
            name="total_purchased",
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                editable=False,
                max_digits=14,
                verbose_name="Сумма закупки",
            ),
        ),
    ]
