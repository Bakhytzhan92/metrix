from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0044_off_estimate_request_items"),
    ]

    operations = [
        migrations.AddField(
            model_name="offestimatesupplyrequestitem",
            name="note",
            field=models.TextField(blank=True, default="", verbose_name="Примечание"),
        ),
        migrations.RemoveField(
            model_name="offestimatesupplyrequestitem",
            name="price_plan",
        ),
        migrations.RemoveField(
            model_name="offestimatesupplyrequestitem",
            name="total_plan",
        ),
        migrations.RemoveField(
            model_name="offestimatesupplyrequestitem",
            name="total_purchased",
        ),
        migrations.RemoveField(
            model_name="offestimatesupplyrequest",
            name="total_plan",
        ),
        migrations.RemoveField(
            model_name="offestimatesupplyrequest",
            name="total_purchased",
        ),
    ]
