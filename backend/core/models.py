from django.conf import settings
from django.db import models


class Company(models.Model):
    name = models.CharField("Название компании", max_length=255)
    subscription_plan = models.CharField(
        "Тарифный план", max_length=100, default="Trial"
    )
    subscription_expires_at = models.DateField(
        "Срок действия подписки", null=True, blank=True
    )

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="owned_companies",
    )

    def __str__(self) -> str:
        return self.name


# ---------- Роли и доступ (Настройки → Права доступа) ----------


class CompanyRole(models.Model):
    """Роль пользователя в компании (системная или кастомная)."""

    SLUG_OWNER = "owner"
    SLUG_MANAGER = "manager"
    SLUG_EMPLOYEE = "employee"

    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="roles"
    )
    name = models.CharField("Название", max_length=100)
    description = models.TextField("Описание", blank=True)
    is_system = models.BooleanField("Системная роль", default=False)
    slug = models.CharField(
        "Код (для системных ролей)",
        max_length=30,
        blank=True,
        help_text="owner / manager / employee для системных ролей",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Роль в компании"
        verbose_name_plural = "Роли в компании"
        ordering = ["is_system", "name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.company.name})"


class CompanyUser(models.Model):
    """Связь пользователя с компанией и ролью."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="company_users",
    )
    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="company_users"
    )
    role = models.ForeignKey(
        CompanyRole,
        on_delete=models.PROTECT,
        related_name="company_users",
        null=True,
        blank=True,
        help_text="Пусто = доступ только через владельца (legacy).",
    )
    is_active = models.BooleanField("Активен", default=True)
    auto_add_to_new_projects = models.BooleanField(
        "Автоматически добавлять в новые проекты", default=False
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Пользователь компании"
        verbose_name_plural = "Пользователи компании"
        unique_together = [["user", "company"]]
        ordering = ["user__username"]

    def __str__(self) -> str:
        return f"{self.user.get_username()} — {self.company.name}"

    @property
    def is_owner_role(self) -> bool:
        return self.role_id and self.role.slug == CompanyRole.SLUG_OWNER


class ProjectAccess(models.Model):
    """Доступ пользователя к проекту (роль в проекте).

    Исполнитель — прораб (отчёты и фото в «Стройке»).
    Наблюдатель — клиент / только просмотр стройки и разделов без редактирования очередей.
    """

    ROLE_MANAGER = "manager"
    ROLE_WORKER = "worker"
    ROLE_VIEWER = "viewer"
    ROLE_CHOICES = [
        (ROLE_MANAGER, "Руководитель проекта"),
        (ROLE_WORKER, "Исполнитель (прораб)"),
        (ROLE_VIEWER, "Наблюдатель (только просмотр)"),
    ]

    company_user = models.ForeignKey(
        CompanyUser,
        on_delete=models.CASCADE,
        related_name="project_accesses",
    )
    project = models.ForeignKey(
        "Project", on_delete=models.CASCADE, related_name="project_accesses"
    )
    role_in_project = models.CharField(
        "Роль в проекте",
        max_length=20,
        choices=ROLE_CHOICES,
        default=ROLE_VIEWER,
    )

    class Meta:
        verbose_name = "Доступ к проекту"
        verbose_name_plural = "Доступы к проектам"
        unique_together = [["company_user", "project"]]
        ordering = ["project__name"]

    def __str__(self) -> str:
        return f"{self.company_user.user.get_username()} — {self.project.name} ({self.get_role_in_project_display()})"


class Project(models.Model):
    STATUS_CHOICES = [
        ("planning", "Планирование"),
        ("active", "Активный"),
        ("completed", "Завершён"),
        ("archived", "Архив"),
    ]

    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="projects"
    )
    name = models.CharField("Название проекта", max_length=255)
    status = models.CharField(
        "Статус", max_length=20, choices=STATUS_CHOICES, default="planning"
    )
    start_date = models.DateField("Дата начала", null=True, blank=True)
    end_date = models.DateField("Дата окончания", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    estimate_vat_enabled = models.BooleanField(
        "Учитывать НДС 16% в итогах для заказчика",
        default=False,
    )

    def __str__(self) -> str:
        return self.name


class EstimateSection(models.Model):
    """Раздел работ сметы (например: Земляные работы, Фундаменты)."""

    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="estimate_sections"
    )
    name = models.CharField("Название раздела", max_length=255)
    order = models.PositiveIntegerField("Порядок", default=0)

    class Meta:
        ordering = ["order", "id"]
        verbose_name = "Раздел сметы"
        verbose_name_plural = "Разделы сметы"

    def __str__(self) -> str:
        return self.name

    @property
    def section_total_cost(self):
        from decimal import Decimal
        return sum((i.total_cost for i in self.items.all()), Decimal("0"))

    @property
    def section_total_price(self):
        from decimal import Decimal
        return sum((i.total_price for i in self.items.all()), Decimal("0"))


class EstimateItem(models.Model):
    """Позиция сметы внутри раздела."""

    TYPE_MATERIAL = "material"
    TYPE_LABOR = "labor"
    TYPE_EQUIPMENT = "equipment"
    TYPE_DELIVERY = "delivery"
    TYPE_CHOICES = [
        (TYPE_MATERIAL, "Материалы"),
        (TYPE_LABOR, "Работы"),
        (TYPE_EQUIPMENT, "Механизмы"),
        (TYPE_DELIVERY, "Доставка"),
    ]

    section = models.ForeignKey(
        EstimateSection, on_delete=models.CASCADE, related_name="items"
    )
    name = models.CharField("Название", max_length=500, blank=True)
    type = models.CharField(
        "Тип", max_length=20, choices=TYPE_CHOICES, default=TYPE_MATERIAL
    )
    unit = models.CharField("Ед. изм.", max_length=30, default="шт")
    quantity = models.DecimalField(
        "Количество", max_digits=14, decimal_places=4, default=0
    )
    cost_price = models.DecimalField(
        "Цена (себестоимость за ед.)", max_digits=14, decimal_places=2, default=0
    )
    markup_percent = models.DecimalField(
        "Наценка, %",
        max_digits=8,
        decimal_places=2,
        default=0,
        help_text="Цена заказчика за ед. = цена × (1 + наценка / 100)",
    )
    sell_price = models.DecimalField(
        "Цена для заказчика за ед.",
        max_digits=14,
        decimal_places=2,
        default=0,
        editable=False,
    )
    total_cost = models.DecimalField(
        "Себестоимость итого", max_digits=16, decimal_places=2, default=0, editable=False
    )
    total_price = models.DecimalField(
        "Итого для заказчика", max_digits=16, decimal_places=2, default=0, editable=False
    )
    order = models.PositiveIntegerField("Порядок", default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    SCHEDULE_PLANNED = "planned"
    SCHEDULE_IN_PROGRESS = "in_progress"
    SCHEDULE_COMPLETED = "completed"
    SCHEDULE_STATUS_CHOICES = [
        (SCHEDULE_PLANNED, "План"),
        (SCHEDULE_IN_PROGRESS, "В работе"),
        (SCHEDULE_COMPLETED, "Завершено"),
    ]
    schedule_start = models.DateField("График: начало", null=True, blank=True)
    schedule_end = models.DateField("График: окончание", null=True, blank=True)
    schedule_status = models.CharField(
        "График: статус",
        max_length=20,
        choices=SCHEDULE_STATUS_CHOICES,
        default=SCHEDULE_PLANNED,
    )
    schedule_assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="estimate_items_schedule_assigned",
        verbose_name="График: ответственный",
    )
    schedule_predecessor = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="schedule_dependents",
        verbose_name="График: предыдущая позиция",
    )

    # --- Стройка: факт vs план (объёмы из журнала ConstructionWorkLog) ---
    CONSTRUCTION_NOT_STARTED = "not_started"
    CONSTRUCTION_IN_PROGRESS = "in_progress"
    CONSTRUCTION_COMPLETED = "completed"
    CONSTRUCTION_OVERDUE = "overdue"
    CONSTRUCTION_EXEC_STATUS_CHOICES = [
        (CONSTRUCTION_NOT_STARTED, "Не начато"),
        (CONSTRUCTION_IN_PROGRESS, "В работе"),
        (CONSTRUCTION_COMPLETED, "Завершено"),
        (CONSTRUCTION_OVERDUE, "Просрочено"),
    ]
    construction_actual_quantity = models.DecimalField(
        "Стройка: выполнено (факт)",
        max_digits=14,
        decimal_places=4,
        default=0,
        help_text="Сумма объёмов из журнала отчётов прораба.",
    )
    construction_exec_status = models.CharField(
        "Стройка: статус",
        max_length=20,
        choices=CONSTRUCTION_EXEC_STATUS_CHOICES,
        default=CONSTRUCTION_NOT_STARTED,
    )

    class Meta:
        ordering = ["order", "id"]
        verbose_name = "Позиция сметы"
        verbose_name_plural = "Позиции сметы"

    def clean(self):
        from django.core.exceptions import ValidationError

        super().clean()
        if self.schedule_predecessor_id:
            pred = self.schedule_predecessor
            if pred.section.project_id != self.section.project_id:
                raise ValidationError(
                    {
                        "schedule_predecessor": "Предшественник должен быть из сметы того же проекта."
                    }
                )
            if pred.pk == self.pk:
                raise ValidationError(
                    {"schedule_predecessor": "Позиция не может зависеть от самой себя."}
                )
            pend = pred.schedule_end
            if (
                self.schedule_start
                and pend
                and self.schedule_start <= pend
            ):
                raise ValidationError(
                    {
                        "schedule_start": "Дата начала должна быть позже окончания предыдущей позиции в графике."
                    }
                )

    def save(self, *args, **kwargs):
        from decimal import Decimal, ROUND_HALF_UP

        q = self.quantity or Decimal("0")
        cp = self.cost_price or Decimal("0")
        m = (self.markup_percent or Decimal("0")) / Decimal("100")
        self.sell_price = (cp * (Decimal("1") + m)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        self.total_cost = (cp * q).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        self.total_price = (self.sell_price * q).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.name

    @property
    def construction_plan_quantity(self):
        return self.quantity or 0

    @property
    def construction_remainder(self):
        from decimal import Decimal

        plan = self.quantity or Decimal("0")
        act = self.construction_actual_quantity or Decimal("0")
        return max(plan - act, Decimal("0"))

    @property
    def construction_percent_done(self):
        from decimal import Decimal

        plan = self.quantity or Decimal("0")
        if plan <= 0:
            return Decimal("0")
        act = self.construction_actual_quantity or Decimal("0")
        pct = (min(act, plan) / plan) * Decimal("100")
        return min(pct, Decimal("100"))


class ConstructionWorkLog(models.Model):
    """Запись в журнале стройки (отчёт прораба по позиции сметы)."""

    estimate_item = models.ForeignKey(
        EstimateItem,
        on_delete=models.CASCADE,
        related_name="construction_logs",
        verbose_name="Позиция сметы",
    )
    work_date = models.DateField("Дата выполнения")
    volume = models.DecimalField(
        "Объём (за отчёт)",
        max_digits=14,
        decimal_places=4,
        help_text="Прибавляется к факту позиции.",
    )
    comment = models.CharField("Комментарий", max_length=2000, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="construction_work_logs",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-work_date", "-created_at"]
        verbose_name = "Запись журнала стройки"
        verbose_name_plural = "Журнал стройки"

    def __str__(self) -> str:
        return f"{self.estimate_item_id} {self.work_date}"


class ConstructionWorkPhoto(models.Model):
    """Фото к записи журнала (фотофиксация)."""

    work_log = models.ForeignKey(
        ConstructionWorkLog,
        on_delete=models.CASCADE,
        related_name="photos",
        verbose_name="Запись журнала",
    )
    image = models.FileField("Фото", upload_to="construction/%Y/%m/")
    caption = models.CharField("Подпись", max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Фото (стройка)"
        verbose_name_plural = "Фото (стройка)"

    def __str__(self) -> str:
        return f"Фото к записи {self.work_log_id}"


class ProjectSchedulePhase(models.Model):
    """Этап графика работ проекта (диаграмма Ганта), опционально привязан к разделу сметы."""

    STATUS_PLANNED = "planned"
    STATUS_IN_PROGRESS = "in_progress"
    STATUS_COMPLETED = "completed"
    STATUS_CHOICES = [
        (STATUS_PLANNED, "План"),
        (STATUS_IN_PROGRESS, "В работе"),
        (STATUS_COMPLETED, "Завершено"),
    ]

    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="schedule_phases"
    )
    estimate_section = models.ForeignKey(
        EstimateSection,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="schedule_phases",
        verbose_name="Раздел сметы",
    )
    name = models.CharField("Название этапа", max_length=255)
    start_date = models.DateField("Дата начала")
    end_date = models.DateField("Дата окончания")
    progress = models.PositiveSmallIntegerField("Прогресс, %", default=0)
    status = models.CharField(
        "Статус",
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PLANNED,
    )
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="schedule_phases_assigned",
        verbose_name="Ответственный",
    )
    predecessor = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="successors",
        verbose_name="Предыдущий этап (зависимость)",
    )
    order = models.PositiveIntegerField("Порядок", default=0)
    estimate_cost_cache = models.DecimalField(
        "Стоимость по смете (кэш)",
        max_digits=16,
        decimal_places=2,
        null=True,
        blank=True,
    )
    work_volume_cache = models.DecimalField(
        "Объём работ по смете (кэш)",
        max_digits=18,
        decimal_places=4,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order", "id"]
        verbose_name = "Этап графика работ"
        verbose_name_plural = "Этапы графика работ"

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError(
                {"end_date": "Дата окончания не может быть раньше даты начала."}
            )
        if self.predecessor_id:
            if self.predecessor_id == self.pk:
                raise ValidationError(
                    {"predecessor": "Этап не может зависеть от самого себя."}
                )
            if self.predecessor.project_id != self.project_id:
                raise ValidationError(
                    {"predecessor": "Предшественник должен быть из того же проекта."}
                )
            if (
                self.start_date
                and self.predecessor.end_date
                and self.start_date <= self.predecessor.end_date
            ):
                raise ValidationError(
                    {
                        "start_date": "Начало этапа должно быть позже даты окончания предыдущего этапа."
                    }
                )

    @property
    def duration_days(self) -> int:
        if not self.start_date or not self.end_date:
            return 0
        return (self.end_date - self.start_date).days + 1

    def save(self, *args, **kwargs):
        if self.progress is not None:
            self.progress = max(0, min(int(self.progress), 100))
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.name


class Task(models.Model):
    """Задача в рамках проекта. Связана с проектом компании пользователя."""

    STATUS_NEW = "new"
    STATUS_IN_PROGRESS = "in_progress"
    STATUS_DONE = "done"
    STATUS_CANCELED = "canceled"
    STATUS_CHOICES = [
        (STATUS_NEW, "Новая"),
        (STATUS_IN_PROGRESS, "В работе"),
        (STATUS_DONE, "Выполнена"),
        (STATUS_CANCELED, "Отменена"),
    ]

    PRIORITY_LOW = "low"
    PRIORITY_MEDIUM = "medium"
    PRIORITY_HIGH = "high"
    PRIORITY_CHOICES = [
        (PRIORITY_LOW, "Низкий"),
        (PRIORITY_MEDIUM, "Средний"),
        (PRIORITY_HIGH, "Высокий"),
    ]

    # Связь: проект → много задач
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="tasks"
    )
    title = models.CharField("Название", max_length=255)
    description = models.TextField("Описание", blank=True)
    status = models.CharField(
        "Статус",
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_NEW,
    )
    priority = models.CharField(
        "Приоритет",
        max_length=10,
        choices=PRIORITY_CHOICES,
        default=PRIORITY_MEDIUM,
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_tasks",
        verbose_name="Ответственный",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="created_tasks",
        verbose_name="Создал",
        null=True,
        blank=True,
    )
    start_date = models.DateField("Дата начала", null=True, blank=True)
    due_date = models.DateField("Дедлайн", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Задача"
        verbose_name_plural = "Задачи"

    def __str__(self) -> str:
        return self.title


class Finance(models.Model):
    """Упрощённые финансы по проекту (вкладка внутри проекта)."""

    CATEGORY_CHOICES = [
        ("income", "Доход"),
        ("expense", "Расход"),
    ]

    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="finances"
    )
    amount = models.DecimalField("Сумма", max_digits=12, decimal_places=2)
    category = models.CharField(
        "Категория", max_length=10, choices=CATEGORY_CHOICES
    )
    description = models.CharField("Описание", max_length=255, blank=True)
    date = models.DateField("Дата", null=False)

    def __str__(self) -> str:
        sign = "+" if self.category == "income" else "-"
        return f"{self.project.name}: {sign}{self.amount}"


# ---------- Модуль «Финансы»: счета, статьи, журнал операций ----------


class Account(models.Model):
    """Счёт компании (Расчётный счёт, Касса и т.д.)."""

    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="finance_accounts"
    )
    name = models.CharField("Название", max_length=255)
    balance = models.DecimalField(
        "Баланс", max_digits=14, decimal_places=2, default=0
    )
    currency = models.CharField("Валюта", max_length=3, default="KZT")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Счёт"
        verbose_name_plural = "Счета"
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.balance} {self.currency})"


class FinanceCategory(models.Model):
    """Статья доходов/расходов (Оплата поставщикам, Зарплата, Материалы)."""

    TYPE_INCOME = "income"
    TYPE_EXPENSE = "expense"
    TYPE_CHOICES = [
        (TYPE_INCOME, "Доход"),
        (TYPE_EXPENSE, "Расход"),
    ]

    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="finance_categories"
    )
    name = models.CharField("Название", max_length=255)
    type = models.CharField(
        "Тип", max_length=10, choices=TYPE_CHOICES
    )

    # Настройка для отчётов (P&L и Cash Flow). Можно не заполнять — будут применены дефолты в services.
    PNL_REVENUE = "revenue"
    PNL_OTHER_INCOME = "other_income"
    PNL_VARIABLE_EXPENSE = "variable_expense"
    PNL_FIXED_EXPENSE = "fixed_expense"
    PNL_OTHER_EXPENSE = "other_expense"
    PNL_INTEREST = "interest"
    PNL_TAXES = "taxes"
    PNL_DEPRECIATION = "depreciation"
    PNL_GROUP_CHOICES = [
        (PNL_REVENUE, "Выручка"),
        (PNL_OTHER_INCOME, "Прочие доходы"),
        (PNL_VARIABLE_EXPENSE, "Переменные расходы"),
        (PNL_FIXED_EXPENSE, "Постоянные расходы"),
        (PNL_OTHER_EXPENSE, "Прочие расходы"),
        (PNL_INTEREST, "Проценты"),
        (PNL_TAXES, "Налоги"),
        (PNL_DEPRECIATION, "Амортизация"),
    ]
    pnl_group = models.CharField(
        "P&L группа",
        max_length=30,
        choices=PNL_GROUP_CHOICES,
        blank=True,
        default="",
        help_text="Для P&L: куда относить операции по этой статье (если не задано — применятся дефолты).",
    )

    CF_OPERATING = "operating"
    CF_INVESTING = "investing"
    CF_FINANCING = "financing"
    CF_GROUP_CHOICES = [
        (CF_OPERATING, "Операционная деятельность"),
        (CF_INVESTING, "Инвестиционная"),
        (CF_FINANCING, "Финансовая"),
    ]
    cashflow_group = models.CharField(
        "Cash Flow группа",
        max_length=20,
        choices=CF_GROUP_CHOICES,
        blank=True,
        default="",
        help_text="Для Cash Flow: раздел отчёта (если не задано — Операционная).",
    )

    class Meta:
        verbose_name = "Статья"
        verbose_name_plural = "Статьи"
        ordering = ["type", "name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.get_type_display()})"


class ActiveFinanceOperationManager(models.Manager):
    """Исключает soft-deleted операции."""

    def get_queryset(self):
        return super().get_queryset().filter(deleted_at__isnull=True)


class FinanceOperation(models.Model):
    """
    Журнал операций: доход, расход, перевод между счетами.
    При сохранении автоматически пересчитывается balance счёта(ов).
    Расход/перевод проверяет достаточность средств.
    Удаление — soft delete (deleted_at); из журнала скрываются через objects.
    """

    TYPE_INCOME = "income"
    TYPE_EXPENSE = "expense"
    TYPE_TRANSFER = "transfer"
    TYPE_CHOICES = [
        (TYPE_INCOME, "Доход"),
        (TYPE_EXPENSE, "Расход"),
        (TYPE_TRANSFER, "Перевод"),
    ]

    BASIS_MANUAL = "manual"
    BASIS_SUPPLY_ORDER = "supply_order"
    BASIS_WORK_ACT = "work_act"
    BASIS_ESTIMATE = "estimate"
    BASIS_CHOICES = [
        (BASIS_MANUAL, "Вручную"),
        (BASIS_SUPPLY_ORDER, "Заказ поставщику"),
        (BASIS_WORK_ACT, "Акт работ"),
        (BASIS_ESTIMATE, "Смета / план"),
    ]

    JOURNAL_PAID = "paid"
    JOURNAL_PARTIAL = "partial"
    JOURNAL_PLANNED = "planned"
    JOURNAL_STATUS_CHOICES = [
        (JOURNAL_PAID, "Оплачено"),
        (JOURNAL_PARTIAL, "Частично"),
        (JOURNAL_PLANNED, "План"),
    ]

    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="finance_operations"
    )
    account = models.ForeignKey(
        Account, on_delete=models.CASCADE, related_name="operations"
    )
    # Для перевода: счёт назначения (списание с account, зачисление на account_to)
    account_to = models.ForeignKey(
        Account,
        on_delete=models.CASCADE,
        related_name="operations_incoming",
        null=True,
        blank=True,
        verbose_name="Счёт назначения",
    )
    project = models.ForeignKey(
        Project,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="finance_operations",
    )
    category = models.ForeignKey(
        FinanceCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="operations",
    )
    type = models.CharField(
        "Тип", max_length=10, choices=TYPE_CHOICES
    )
    amount = models.DecimalField("Сумма", max_digits=14, decimal_places=2)
    description = models.CharField("Описание", max_length=500, blank=True)
    contractor = models.CharField("Контрагент", max_length=255, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="finance_operations_created",
    )
    date = models.DateField("Дата")
    created_at = models.DateTimeField(auto_now_add=True)
    basis = models.CharField(
        "Основание",
        max_length=20,
        choices=BASIS_CHOICES,
        default=BASIS_MANUAL,
    )
    journal_status = models.CharField(
        "Статус в журнале",
        max_length=10,
        choices=JOURNAL_STATUS_CHOICES,
        default=JOURNAL_PAID,
        help_text="Оплачено/частично/план — для учёта кассовых и обязательств.",
    )
    supply_order = models.ForeignKey(
        "SupplyOrder",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payment_operations",
        verbose_name="Заказ снабжения",
    )
    work_act = models.ForeignKey(
        "WorkAct",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payment_operations",
        verbose_name="Акт работ",
    )
    deleted_at = models.DateTimeField(
        "Удалено",
        null=True,
        blank=True,
        db_index=True,
    )

    objects = ActiveFinanceOperationManager()
    all_objects = models.Manager()

    class Meta:
        ordering = ["-date", "-created_at"]
        verbose_name = "Операция"
        verbose_name_plural = "Журнал операций"

    def __str__(self) -> str:
        return f"{self.get_type_display()} {self.amount} — {self.date}"

    def soft_delete(self):
        """Скрыть операцию и откатить баланс счёта(ов)."""
        from django.db import transaction
        from django.utils import timezone

        if self.deleted_at:
            return
        with transaction.atomic():
            self._apply_balance(reverse=True)
            self.deleted_at = timezone.now()
            models.Model.save(self, update_fields=["deleted_at"])

    def _apply_balance(self, reverse: bool = False):
        """Применить операцию к балансу счёта(ов). reverse=True при удалении/откате."""
        sign = -1 if reverse else 1  # reverse: откат (минус к тому, что применили)

        if self.type == self.TYPE_INCOME:
            self.account.balance += sign * self.amount
            self.account.save(update_fields=["balance"])
        elif self.type == self.TYPE_EXPENSE:
            self.account.balance -= sign * self.amount
            self.account.save(update_fields=["balance"])
        elif self.type == self.TYPE_TRANSFER and self.account_to_id:
            self.account.balance -= sign * self.amount
            self.account_to.balance += sign * self.amount
            self.account.save(update_fields=["balance"])
            self.account_to.save(update_fields=["balance"])

    def save(self, *args, **kwargs):
        """При сохранении пересчитываем баланс. При создании — применяем; при обновлении — откат старого, применение нового."""
        from django.db import transaction

        if self.pk:
            old = FinanceOperation.all_objects.get(pk=self.pk)
            with transaction.atomic():
                old._apply_balance(reverse=True)
                super().save(*args, **kwargs)
                self._apply_balance(reverse=False)
            return
        with transaction.atomic():
            # Проверка: расход/перевод — нельзя списать больше, чем есть
            if self.type in (self.TYPE_EXPENSE, self.TYPE_TRANSFER):
                if self.type == self.TYPE_TRANSFER and self.account_to_id:
                    if self.account_id == self.account_to_id:
                        raise ValueError("Счёт списания и счёт зачисления не должны совпадать.")
                acc = Account.objects.select_for_update().get(pk=self.account_id)
                if acc.balance < self.amount:
                    raise ValueError(
                        f"Недостаточно средств на счёте «{acc.name}». Баланс: {acc.balance}"
                    )
            super().save(*args, **kwargs)
            self._apply_balance(reverse=False)

    def delete(self, *args, **kwargs):
        """При удалении откатываем изменение баланса."""
        from django.db import transaction

        with transaction.atomic():
            self._apply_balance(reverse=True)
            super().delete(*args, **kwargs)


class WorkAct(models.Model):
    """
    Акт выполненных работ (подрядчик).
    Черновик → отправка на оплату → очередь в финансах проекта «Работы на оплату».
    """

    PAYMENT_DRAFT = "draft"
    PAYMENT_AWAITING = "awaiting_payment"
    PAYMENT_PARTIAL = "partial"
    PAYMENT_PAID = "paid"
    PAYMENT_STATUS_CHOICES = [
        (PAYMENT_DRAFT, "Черновик"),
        (PAYMENT_AWAITING, "Ожидает оплаты"),
        (PAYMENT_PARTIAL, "Частично оплачено"),
        (PAYMENT_PAID, "Оплачено"),
    ]

    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="work_acts"
    )
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="work_acts"
    )
    contractor = models.CharField("Подрядчик", max_length=255)
    work_type = models.CharField("Вид работ", max_length=500, blank=True)
    amount = models.DecimalField("Сумма акта", max_digits=16, decimal_places=2)
    act_date = models.DateField("Дата акта")
    payment_status = models.CharField(
        "Статус оплаты",
        max_length=20,
        choices=PAYMENT_STATUS_CHOICES,
        default=PAYMENT_DRAFT,
    )
    paid_amount = models.DecimalField(
        "Оплачено", max_digits=16, decimal_places=2, default=0
    )
    description = models.CharField("Комментарий", max_length=500, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="work_acts_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-act_date", "-created_at"]
        verbose_name = "Акт работ"
        verbose_name_plural = "Акты работ"

    def __str__(self) -> str:
        return f"{self.contractor} — {self.act_date}"

    @property
    def remaining_amount(self):
        from decimal import Decimal

        a = self.amount or Decimal("0")
        p = self.paid_amount or Decimal("0")
        return max(a - p, Decimal("0"))


# ---------- Модуль «Снабжение»: ресурсы, заявки, заказы ----------
# Расширяемо: склады, остатки, план/факт; связь заказ → финансы (оплата) — позже.


class Resource(models.Model):
    """Ресурс / материал компании (справочник для заявок)."""

    TYPE_MATERIAL = "material"
    TYPE_SERVICE = "service"
    TYPE_EQUIPMENT = "equipment"
    TYPE_LABOR = "labor"
    TYPE_CHOICES = [
        (TYPE_MATERIAL, "Материал"),
        (TYPE_LABOR, "Труд / люди"),
        (TYPE_SERVICE, "Услуга"),
        (TYPE_EQUIPMENT, "Механизмы"),
    ]

    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="supply_resources"
    )
    name = models.CharField("Название", max_length=255)
    type = models.CharField(
        "Тип", max_length=20, choices=TYPE_CHOICES, default=TYPE_MATERIAL
    )
    unit = models.CharField("Единица", max_length=50, default="шт.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Ресурс"
        verbose_name_plural = "Ресурсы"
        ordering = ["type", "name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.get_type_display()})"


class SupplyRequest(models.Model):
    """
    Заявка на снабжение. Связь смета → заявка → заказ → финансы / склад.
    """

    STATUS_DRAFT = "draft"
    STATUS_PENDING = "pending"
    STATUS_IN_PROGRESS = "in_progress"
    STATUS_PARTIAL = "partial"
    STATUS_PURCHASED = "purchased"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Черновик"),
        (STATUS_PENDING, "Ожидает закупки"),
        (STATUS_IN_PROGRESS, "В закупке"),
        (STATUS_PARTIAL, "Частично закуплено"),
        (STATUS_PURCHASED, "Закуплено"),
        (STATUS_CANCELLED, "Отменена"),
    ]

    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="supply_requests"
    )
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="supply_requests"
    )
    resource = models.ForeignKey(
        Resource, on_delete=models.CASCADE, related_name="requests"
    )
    estimate_item = models.ForeignKey(
        "EstimateItem",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="supply_requests",
        verbose_name="Позиция сметы",
    )
    required_date = models.DateField("Потребуется")
    delivery_date = models.DateField(
        "Срок доставки", null=True, blank=True
    )
    quantity = models.DecimalField(
        "Количество", max_digits=14, decimal_places=4, default=0
    )
    quantity_received = models.DecimalField(
        "Закуплено (факт, кол-во)", max_digits=14, decimal_places=4, default=0
    )
    price_plan = models.DecimalField(
        "Цена за ед., план", max_digits=14, decimal_places=2, default=0
    )
    total_plan = models.DecimalField(
        "План, сумма", max_digits=14, decimal_places=2, default=0, editable=False
    )
    supplier_name = models.CharField(
        "Поставщик (заявка)", max_length=255, blank=True
    )
    status = models.CharField(
        "Статус",
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_DRAFT,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="supply_requests_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-required_date", "-created_at"]
        verbose_name = "Заявка"
        verbose_name_plural = "Заявки"

    def __str__(self) -> str:
        return f"{self.resource.name} — {self.required_date}"

    @property
    def total_fact_ordered(self):
        """Сумма факт по заказу (если позиция в заказе)."""
        from decimal import Decimal

        oi = getattr(self, "order_item", None)
        if oi:
            return oi.total_fact
        return Decimal("0")

    def save(self, *args, **kwargs):
        from decimal import Decimal, ROUND_HALF_UP

        q = self.quantity or Decimal("0")
        p = self.price_plan or Decimal("0")
        self.total_plan = (q * p).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        super().save(*args, **kwargs)


class SupplyOrder(models.Model):
    """
    Заказ поставщику. Несколько заявок (SupplyOrderItem) → расход в Финансах.
    """

    STATUS_NEW = "new"
    STATUS_PAID = "paid"
    STATUS_DELIVERED = "delivered"
    STATUS_CLOSED = "closed"
    STATUS_CHOICES = [
        (STATUS_NEW, "Новый"),
        (STATUS_PAID, "Оплачен"),
        (STATUS_DELIVERED, "Поставлен"),
        (STATUS_CLOSED, "Закрыт"),
    ]

    PAYMENT_DRAFT = "draft"
    PAYMENT_AWAITING = "awaiting_payment"
    PAYMENT_PARTIAL = "partial"
    PAYMENT_PAID = "paid"
    PAYMENT_STATUS_CHOICES = [
        (PAYMENT_DRAFT, "Черновик"),
        (PAYMENT_AWAITING, "Ожидает оплаты"),
        (PAYMENT_PARTIAL, "Частично оплачено"),
        (PAYMENT_PAID, "Оплачено"),
    ]

    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="supply_orders"
    )
    project = models.ForeignKey(
        Project,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="supply_orders",
        verbose_name="Проект",
    )
    supplier = models.CharField("Поставщик", max_length=255)
    status = models.CharField(
        "Статус поставки", max_length=20, choices=STATUS_CHOICES, default=STATUS_NEW
    )
    payment_status = models.CharField(
        "Оплата",
        max_length=20,
        choices=PAYMENT_STATUS_CHOICES,
        default=PAYMENT_DRAFT,
    )
    paid_amount = models.DecimalField(
        "Оплачено по заказу", max_digits=16, decimal_places=2, default=0
    )
    total_amount = models.DecimalField(
        "Сумма заказа", max_digits=16, decimal_places=2, default=0, editable=False
    )
    finance_operation = models.ForeignKey(
        "FinanceOperation",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="supply_orders",
        verbose_name="Операция в финансах",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Заказ"
        verbose_name_plural = "Заказы"

    def __str__(self) -> str:
        return f"{self.supplier} — {self.get_status_display()}"

    def recalc_total(self):
        from decimal import Decimal, ROUND_HALF_UP

        from django.db.models import Sum

        agg = self.items.aggregate(s=Sum("total_fact"))
        v = agg.get("s")
        if v is None:
            v = Decimal("0")
        else:
            v = Decimal(str(v))
        self.total_amount = v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @property
    def remaining_amount(self):
        from decimal import Decimal

        t = self.total_amount or Decimal("0")
        p = self.paid_amount or Decimal("0")
        return max(t - p, Decimal("0"))


class SupplyOrderItem(models.Model):
    """Позиция заказа: связь заказ ↔ заявка, факт количества и цены."""

    order = models.ForeignKey(
        SupplyOrder, on_delete=models.CASCADE, related_name="items"
    )
    request = models.OneToOneField(
        SupplyRequest,
        on_delete=models.CASCADE,
        related_name="order_item",
        null=True,
        blank=True,
    )
    quantity = models.DecimalField(
        "Количество", max_digits=14, decimal_places=4, default=0
    )
    price_fact = models.DecimalField(
        "Цена, факт", max_digits=14, decimal_places=2, default=0
    )
    total_fact = models.DecimalField(
        "Факт, сумма", max_digits=14, decimal_places=2, default=0, editable=False
    )

    class Meta:
        verbose_name = "Позиция заказа"
        verbose_name_plural = "Позиции заказа"

    def save(self, *args, **kwargs):
        self.total_fact = self.quantity * self.price_fact
        super().save(*args, **kwargs)


# ---------- Модуль «Склады»: склады, остатки, операции ----------
# Связь: заказ снабжения → поступление на склад; задача → списание (позже).
# Остатки: пересчёт при каждой операции (price_avg при поступлении).


class Warehouse(models.Model):
    """Склад компании. project задан для приобъектного склада."""

    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="warehouses"
    )
    name = models.CharField("Название", max_length=255)
    location = models.CharField("Локация", max_length=255, blank=True)
    project = models.ForeignKey(
        Project,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="warehouses",
        verbose_name="Проект (приобъектный)",
    )
    is_deleted = models.BooleanField("Удалён", default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Склад"
        verbose_name_plural = "Склады"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


# ---------- Новая модель складов: Material, Stock, StockMovement ----------


class Material(models.Model):
    """Материал / инструмент / оборудование (справочник компании)."""

    CATEGORY_MATERIAL = "material"
    CATEGORY_TOOL = "tool"
    CATEGORY_EQUIPMENT = "equipment"
    CATEGORY_CHOICES = [
        (CATEGORY_MATERIAL, "Материал"),
        (CATEGORY_TOOL, "Инструмент"),
        (CATEGORY_EQUIPMENT, "Оборудование"),
    ]

    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="materials"
    )
    name = models.CharField("Название", max_length=255)
    unit = models.CharField("Ед. изм.", max_length=30, default="шт")
    category = models.CharField(
        "Категория", max_length=20, choices=CATEGORY_CHOICES, default=CATEGORY_MATERIAL
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Материал"
        verbose_name_plural = "Материалы"
        ordering = ["category", "name"]
        unique_together = [["company", "name"]]

    def __str__(self) -> str:
        return self.name


class Stock(models.Model):
    """Остаток материала на складе. Обновляется при операциях (incoming/transfer/writeoff/outgoing)."""

    warehouse = models.ForeignKey(
        Warehouse, on_delete=models.CASCADE, related_name="stocks"
    )
    material = models.ForeignKey(
        Material, on_delete=models.CASCADE, related_name="stocks"
    )
    quantity = models.DecimalField(
        "Количество", max_digits=14, decimal_places=4, default=0
    )
    price_avg = models.DecimalField(
        "Средняя цена", max_digits=14, decimal_places=2, default=0
    )

    class Meta:
        unique_together = [["warehouse", "material"]]
        verbose_name = "Остаток (Stock)"
        verbose_name_plural = "Остатки (Stock)"

    @property
    def total_sum(self):
        from decimal import Decimal
        return (self.quantity or Decimal("0")) * (self.price_avg or Decimal("0"))

    def __str__(self) -> str:
        return f"{self.material.name} @ {self.warehouse.name}: {self.quantity}"


class StockMovement(models.Model):
    """Движение материала: поступление, списание на объект, перемещение, списание."""

    TYPE_INCOMING = "incoming"
    TYPE_OUTGOING = "outgoing"
    TYPE_TRANSFER = "transfer"
    TYPE_WRITEOFF = "writeoff"
    TYPE_CHOICES = [
        (TYPE_INCOMING, "Поступление"),
        (TYPE_OUTGOING, "Списание на объект"),
        (TYPE_TRANSFER, "Перемещение"),
        (TYPE_WRITEOFF, "Списание"),
    ]

    material = models.ForeignKey(
        Material, on_delete=models.CASCADE, related_name="movements"
    )
    warehouse_from = models.ForeignKey(
        Warehouse,
        on_delete=models.CASCADE,
        related_name="movements_out",
        null=True,
        blank=True,
        verbose_name="Склад откуда",
    )
    warehouse_to = models.ForeignKey(
        Warehouse,
        on_delete=models.CASCADE,
        related_name="movements_in",
        null=True,
        blank=True,
        verbose_name="Склад куда",
    )
    project = models.ForeignKey(
        Project,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stock_movements",
        verbose_name="Проект (при списании на объект)",
    )
    movement_type = models.CharField(
        "Тип операции", max_length=20, choices=TYPE_CHOICES
    )
    quantity = models.DecimalField("Количество", max_digits=14, decimal_places=4)
    price = models.DecimalField(
        "Цена за ед.", max_digits=14, decimal_places=2, default=0
    )
    total = models.DecimalField(
        "Сумма", max_digits=16, decimal_places=2, default=0, editable=False
    )
    date = models.DateField("Дата")
    comment = models.CharField("Комментарий", max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-created_at"]
        verbose_name = "Движение"
        verbose_name_plural = "Движения"

    def save(self, *args, **kwargs):
        from decimal import Decimal
        self.total = (self.quantity or Decimal("0")) * (self.price or Decimal("0"))
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.get_movement_type_display()} {self.material.name} {self.quantity}"


# ---------- Инвентарь (оборудование, инструменты): Kanban, статусы, история ----------


class WarehouseInventoryItem(models.Model):
    """Единица инвентаря (оборудование, инструмент) на складе."""

    STATUS_FREE = "free"
    STATUS_IN_USE = "in_use"
    STATUS_BROKEN = "broken"
    STATUS_WRITTEN_OFF = "written_off"
    STATUS_CHOICES = [
        (STATUS_FREE, "Свободен"),
        (STATUS_IN_USE, "В работе"),
        (STATUS_BROKEN, "Сломан"),
        (STATUS_WRITTEN_OFF, "Списан"),
    ]

    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="warehouse_inventory_items"
    )
    warehouse = models.ForeignKey(
        Warehouse, on_delete=models.CASCADE, related_name="warehouse_inventory_items"
    )
    name = models.CharField("Название", max_length=500)
    inventory_number = models.CharField("Инвентарный номер", max_length=100, blank=True)
    status = models.CharField(
        "Статус", max_length=20, choices=STATUS_CHOICES, default=STATUS_FREE
    )
    purchase_price = models.DecimalField(
        "Стоимость (₽)", max_digits=14, decimal_places=2, default=0, null=True, blank=True
    )
    purchase_date = models.DateField("Дата покупки", null=True, blank=True)
    description = models.TextField("Описание", blank=True)
    image = models.FileField(
        "Фото", upload_to="inventory/", null=True, blank=True
    )
    available_from = models.DateField(
        "Будет свободен", null=True, blank=True,
        help_text="Дата освобождения при статусе «В работе»",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        verbose_name = "Инвентарь"
        verbose_name_plural = "Инвентарь"

    def __str__(self) -> str:
        return self.name


class InventoryTransfer(models.Model):
    """Перемещение единицы инвентаря между складами."""

    item = models.ForeignKey(
        WarehouseInventoryItem, on_delete=models.CASCADE, related_name="transfers"
    )
    from_warehouse = models.ForeignKey(
        Warehouse, on_delete=models.CASCADE, related_name="transfers_out", null=True, blank=True
    )
    to_warehouse = models.ForeignKey(
        Warehouse, on_delete=models.CASCADE, related_name="transfers_in"
    )
    date = models.DateTimeField("Дата")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="inventory_transfers",
    )

    class Meta:
        ordering = ["-date"]
        verbose_name = "Перемещение инвентаря"
        verbose_name_plural = "Перемещения инвентаря"

    def __str__(self) -> str:
        return f"{self.item.name} → {self.to_warehouse.name}"


class InventoryLog(models.Model):
    """История действий по инвентарю."""

    ACTION_CREATED = "created"
    ACTION_MOVED = "moved"
    ACTION_UPDATED = "updated"
    ACTION_STATUS_CHANGED = "status_changed"
    ACTION_CHOICES = [
        (ACTION_CREATED, "Создан инвентарь"),
        (ACTION_MOVED, "Перемещён"),
        (ACTION_UPDATED, "Изменён"),
        (ACTION_STATUS_CHANGED, "Изменён статус"),
    ]

    item = models.ForeignKey(
        WarehouseInventoryItem, on_delete=models.CASCADE, related_name="logs"
    )
    action = models.CharField("Действие", max_length=20, choices=ACTION_CHOICES)
    description = models.CharField("Описание", max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="inventory_logs",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Запись истории инвентаря"
        verbose_name_plural = "История инвентаря"

    def __str__(self) -> str:
        return f"{self.item.name}: {self.get_action_display()}"


class StockItem(models.Model):
    """Остаток по ресурсу на складе. Обновляется при поступлении/списании/перемещении."""

    warehouse = models.ForeignKey(
        Warehouse, on_delete=models.CASCADE, related_name="stock_items"
    )
    resource = models.ForeignKey(
        Resource, on_delete=models.CASCADE, related_name="stock_items"
    )
    quantity = models.DecimalField(
        "Количество", max_digits=14, decimal_places=4, default=0
    )
    price_avg = models.DecimalField(
        "Средняя цена", max_digits=14, decimal_places=2, default=0
    )
    total_sum = models.DecimalField(
        "Сумма", max_digits=14, decimal_places=2, default=0, editable=False
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [["warehouse", "resource"]]
        verbose_name = "Остаток"
        verbose_name_plural = "Остатки"

    def save(self, *args, **kwargs):
        self.total_sum = self.quantity * self.price_avg
        super().save(*args, **kwargs)


class WarehouseOperation(models.Model):
    """
    Операция на складе: поступление, списание или перемещение.
    При поступлении — увеличиваем остаток, пересчитываем price_avg.
    При списании — уменьшаем остаток (не больше имеющегося).
    При перемещении — списание с from_warehouse, поступление на to_warehouse.
    """

    TYPE_INCOMING = "incoming"
    TYPE_OUTGOING = "outgoing"
    TYPE_TRANSFER = "transfer"
    TYPE_CHOICES = [
        (TYPE_INCOMING, "Поступление"),
        (TYPE_OUTGOING, "Списание"),
        (TYPE_TRANSFER, "Перемещение"),
    ]

    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="warehouse_operations"
    )
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.CASCADE,
        related_name="operations",
        null=True,
        blank=True,
        help_text="Для поступления/списания — склад; для перемещения — не используется",
    )
    resource = models.ForeignKey(
        Resource, on_delete=models.CASCADE, related_name="warehouse_operations"
    )
    operation_type = models.CharField(
        "Тип", max_length=20, choices=TYPE_CHOICES
    )
    quantity = models.DecimalField("Количество", max_digits=14, decimal_places=4)
    price = models.DecimalField("Цена", max_digits=14, decimal_places=2, default=0)
    total = models.DecimalField(
        "Сумма", max_digits=14, decimal_places=2, default=0, editable=False
    )
    order = models.ForeignKey(
        SupplyOrder,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="warehouse_operations",
        verbose_name="Заказ снабжения",
    )
    from_warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.CASCADE,
        related_name="operations_out",
        null=True,
        blank=True,
        verbose_name="Со склада",
    )
    to_warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.CASCADE,
        related_name="operations_in",
        null=True,
        blank=True,
        verbose_name="На склад",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="warehouse_operations_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Операция склада"
        verbose_name_plural = "Операции склада"

    def __str__(self) -> str:
        return f"{self.get_operation_type_display()} {self.resource.name} — {self.created_at:%Y-%m-%d}"

    def save(self, *args, **kwargs):
        from decimal import Decimal
        from django.db import transaction

        self.total = self.quantity * self.price

        with transaction.atomic():
            if self.operation_type == self.TYPE_INCOMING:
                if not self.warehouse_id:
                    raise ValueError("Для поступления укажите склад.")
                item, _ = StockItem.objects.select_for_update().get_or_create(
                    warehouse=self.warehouse,
                    resource=self.resource,
                    defaults={"quantity": 0, "price_avg": 0},
                )
                new_qty = item.quantity + self.quantity
                new_total = item.total_sum + self.total
                item.price_avg = new_total / new_qty if new_qty else Decimal("0")
                item.quantity = new_qty
                item.save()
            elif self.operation_type == self.TYPE_OUTGOING:
                if not self.warehouse_id:
                    raise ValueError("Для списания укажите склад.")
                item = StockItem.objects.select_for_update().get(
                    warehouse=self.warehouse, resource=self.resource
                )
                if item.quantity < self.quantity:
                    raise ValueError(
                        f"Недостаточно на складе «{self.warehouse.name}». Остаток: {item.quantity} {self.resource.unit}"
                    )
                item.quantity -= self.quantity
                item.total_sum = item.quantity * item.price_avg
                item.save()
            elif self.operation_type == self.TYPE_TRANSFER:
                if not self.from_warehouse_id or not self.to_warehouse_id:
                    raise ValueError("Для перемещения укажите склад отправления и склад назначения.")
                if self.from_warehouse_id == self.to_warehouse_id:
                    raise ValueError("Склады должны различаться.")
                out_item = StockItem.objects.select_for_update().get(
                    warehouse=self.from_warehouse, resource=self.resource
                )
                if out_item.quantity < self.quantity:
                    raise ValueError(
                        f"Недостаточно на складе «{self.from_warehouse.name}». Остаток: {out_item.quantity}"
                    )
                out_item.quantity -= self.quantity
                out_item.total_sum = out_item.quantity * out_item.price_avg
                out_item.save()
                to_item, _ = StockItem.objects.select_for_update().get_or_create(
                    warehouse=self.to_warehouse,
                    resource=self.resource,
                    defaults={"quantity": 0, "price_avg": 0},
                )
                move_price = self.price or out_item.price_avg
                move_total = self.quantity * move_price
                new_qty = to_item.quantity + self.quantity
                new_total = to_item.total_sum + move_total
                to_item.price_avg = new_total / new_qty if new_qty else Decimal("0")
                to_item.quantity = new_qty
                to_item.save()
        super().save(*args, **kwargs)


class InventoryItem(models.Model):
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="inventory_items"
    )
    name = models.CharField("Название", max_length=255)
    quantity = models.PositiveIntegerField("Количество", default=0)
    unit = models.CharField("Единица измерения", max_length=50, default="шт.")

    def __str__(self) -> str:
        return f"{self.name} ({self.quantity} {self.unit})"


class GeneratedContent(models.Model):
    """
    Заготовка под будущую AI‑интеграцию.

    Здесь в будущем можно вызывать вашу AI‑модель (OpenAI, локальную LLM и т.п.)
    и сохранять промпт и результат.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="generated_contents",
    )
    prompt = models.TextField("Запрос")
    result = models.TextField("Результат")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.user} — {self.created_at:%Y-%m-%d %H:%M}"

