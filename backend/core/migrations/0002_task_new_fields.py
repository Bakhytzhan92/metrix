# Модуль «Задачи»: новые поля и переименования

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def status_todo_to_new(apps, schema_editor):
    """Миграция данных: старый статус 'todo' → 'new'."""
    Task = apps.get_model("core", "Task")
    Task.objects.filter(status="todo").update(status="new")


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.RenameField(
            model_name="task",
            old_name="assignee",
            new_name="assigned_to",
        ),
        migrations.RenameField(
            model_name="task",
            old_name="deadline",
            new_name="due_date",
        ),
        migrations.AddField(
            model_name="task",
            name="description",
            field=models.TextField(blank=True, default="", verbose_name="Описание"),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name="task",
            name="priority",
            field=models.CharField(
                choices=[
                    ("low", "Низкий"),
                    ("medium", "Средний"),
                    ("high", "Высокий"),
                ],
                default="medium",
                max_length=10,
                verbose_name="Приоритет",
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="task",
            name="created_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="created_tasks",
                to=settings.AUTH_USER_MODEL,
                verbose_name="Создал",
            ),
        ),
        migrations.AddField(
            model_name="task",
            name="start_date",
            field=models.DateField(blank=True, null=True, verbose_name="Дата начала"),
        ),
        migrations.AlterField(
            model_name="task",
            name="status",
            field=models.CharField(
                choices=[
                    ("new", "Новая"),
                    ("in_progress", "В работе"),
                    ("done", "Выполнена"),
                    ("canceled", "Отменена"),
                ],
                default="new",
                max_length=20,
                verbose_name="Статус",
            ),
        ),
        migrations.RunPython(status_todo_to_new, noop),
    ]
