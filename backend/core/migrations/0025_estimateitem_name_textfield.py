# Generated manually for long estimate line names (local PDF estimates)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0024_companyuser_role_set_null"),
    ]

    operations = [
        migrations.AlterField(
            model_name="estimateitem",
            name="name",
            field=models.TextField(blank=True, verbose_name="Название"),
        ),
    ]
