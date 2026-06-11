from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0056_timesheet_month_roster"),
    ]

    operations = [
        migrations.AlterField(
            model_name="supplyorderdocument",
            name="doc_type",
            field=models.CharField(
                choices=[
                    ("kp", "Коммерческое предложение"),
                    ("invoice", "Счёт на оплату"),
                    ("payment_proof", "Платёжное поручение"),
                ],
                max_length=16,
                verbose_name="Тип",
            ),
        ),
    ]
