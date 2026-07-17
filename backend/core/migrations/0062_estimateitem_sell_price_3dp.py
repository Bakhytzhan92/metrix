from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0061_supply_order_poa_document"),
    ]

    operations = [
        migrations.AlterField(
            model_name="estimateitem",
            name="sell_price",
            field=models.DecimalField(
                decimal_places=3,
                default=0,
                editable=False,
                max_digits=14,
                verbose_name="Цена для заказчика за ед.",
            ),
        ),
    ]
