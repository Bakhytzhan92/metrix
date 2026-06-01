from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0047_supply_workflow_rbac"),
    ]

    operations = [
        migrations.AddField(
            model_name="company",
            name="off_estimate_excel_header_text",
            field=models.TextField(
                blank=True,
                default="",
                help_text=(
                    "Текст шапки для экспорта заявки. Плейсхолдеры: "
                    "{project}, {date}, {number}, {company}. "
                    "Если загружен файл шаблона — он имеет приоритет над текстом."
                ),
                verbose_name="Шапка Excel заявки вне сметы",
            ),
        ),
        migrations.AddField(
            model_name="company",
            name="off_estimate_excel_header_template",
            field=models.FileField(
                blank=True,
                help_text="Excel-файл (.xlsx): строки первого листа вставляются в верх документа.",
                null=True,
                upload_to="company/off_estimate_excel_headers/",
                verbose_name="Файл шаблона шапки Excel",
            ),
        ),
    ]
