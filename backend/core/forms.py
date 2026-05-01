from decimal import Decimal

from django import forms
from django.contrib.auth.forms import PasswordChangeForm, UserCreationForm
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError

from .account_email import (
    is_registration_email_taken,
    normalize_email,
)

from .models import (
    Company,
    CompanyRole,
    CompanyUser,
    Project,
    ProjectAccess,
    Task,
    Finance,
    InventoryItem,
    Account,
    FinanceCategory,
    FinanceOperation,
    WorkAct,
    Resource,
    SupplyRequest,
    SupplyOrder,
    SupplyOrderItem,
    Warehouse,
    StockItem,
    WarehouseOperation,
    EstimateSection,
    EstimateItem,
    ProjectSchedulePhase,
    Material,
    Stock,
    StockMovement,
    WarehouseInventoryItem,
)


class RegisterForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = ("username", "email", "password1", "password2")

    def clean_email(
        self,
    ):
        email = normalize_email(
            self.cleaned_data.get(
                "email",
            ),
        )
        if not email:
            raise ValidationError(
                "Укажите email.",
            )
        if is_registration_email_taken(
            email,
        ):
            raise ValidationError(
                "Пользователь с таким email уже зарегистрирован. "
                "Войдите в систему или используйте другой адрес.",
            )
        return email

    def save(
        self,
        commit=True,
    ):
        user = super().save(
            commit=False,
        )
        user.email = normalize_email(
            self.cleaned_data.get(
                "email",
            ),
        )
        if commit:
            user.save()
            if hasattr(
                self,
                "save_m2m",
            ):
                self.save_m2m()
        return user


class StyledPasswordChangeForm(PasswordChangeForm):
    """Смена пароля со стилями под Metrix."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        css = (
            "w-full rounded-md border border-slate-300 px-3 py-2 text-sm "
            "focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
        )
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", css)


class CompanyForm(forms.ModelForm):
    class Meta:
        model = Company
        fields = ("name", "subscription_plan", "subscription_expires_at")
        widgets = {
            "subscription_expires_at": forms.DateInput(attrs={"type": "date"}),
        }


class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = ("name", "status", "start_date", "end_date")
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
        }


def _input_class():
    return "w-full rounded-md border-slate-300 text-sm focus:border-indigo-500 focus:ring-indigo-500"


class TaskForm(forms.ModelForm):
    """Форма создания/редактирования задачи (полная, для /tasks/)."""

    class Meta:
        model = Task
        fields = (
            "title",
            "description",
            "project",
            "status",
            "priority",
            "assigned_to",
            "start_date",
            "due_date",
        )
        widgets = {
            "title": forms.TextInput(attrs={"class": _input_class()}),
            "description": forms.Textarea(attrs={"rows": 3, "class": _input_class()}),
            "project": forms.Select(attrs={"class": _input_class()}),
            "status": forms.Select(attrs={"class": _input_class()}),
            "priority": forms.Select(attrs={"class": _input_class()}),
            "assigned_to": forms.Select(attrs={"class": _input_class()}),
            "start_date": forms.DateInput(attrs={"type": "date", "class": _input_class()}),
            "due_date": forms.DateInput(attrs={"type": "date", "class": _input_class()}),
        }


class TaskQuickForm(forms.ModelForm):
    """Краткая форма задачи внутри проекта (без выбора проекта)."""

    class Meta:
        model = Task
        fields = ("title", "status", "priority", "assigned_to", "due_date")
        widgets = {
            "title": forms.TextInput(attrs={"class": _input_class()}),
            "status": forms.Select(attrs={"class": _input_class()}),
            "priority": forms.Select(attrs={"class": _input_class()}),
            "assigned_to": forms.Select(attrs={"class": _input_class()}),
            "due_date": forms.DateInput(attrs={"type": "date", "class": _input_class()}),
        }


class FinanceForm(forms.ModelForm):
    class Meta:
        model = Finance
        fields = ("amount", "category", "description", "date")
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
        }


class InventoryItemForm(forms.ModelForm):
    class Meta:
        model = InventoryItem
        fields = ("name", "quantity", "unit")


# ---------- Модуль «Финансы»: журнал операций ----------


class FinanceIncomeForm(forms.ModelForm):
    """Форма операции «Доход»."""

    class Meta:
        model = FinanceOperation
        fields = ("account", "category", "project", "amount", "description", "contractor", "date")
        widgets = {
            "date": forms.DateInput(attrs={"type": "date", "class": _input_class()}),
            "amount": forms.NumberInput(attrs={"class": _input_class(), "step": "0.01"}),
            "description": forms.Textarea(attrs={"rows": 2, "class": _input_class()}),
            "contractor": forms.TextInput(attrs={"class": _input_class()}),
            "account": forms.Select(attrs={"class": _input_class()}),
            "category": forms.Select(attrs={"class": _input_class()}),
            "project": forms.Select(attrs={"class": _input_class()}),
        }


class FinanceExpenseForm(forms.ModelForm):
    """Форма операции «Расход»."""

    class Meta:
        model = FinanceOperation
        fields = ("account", "category", "project", "amount", "description", "contractor", "date")
        widgets = {
            "date": forms.DateInput(attrs={"type": "date", "class": _input_class()}),
            "amount": forms.NumberInput(attrs={"class": _input_class(), "step": "0.01"}),
            "description": forms.Textarea(attrs={"rows": 2, "class": _input_class()}),
            "contractor": forms.TextInput(attrs={"class": _input_class()}),
            "account": forms.Select(attrs={"class": _input_class()}),
            "category": forms.Select(attrs={"class": _input_class()}),
            "project": forms.Select(attrs={"class": _input_class()}),
        }


class FinanceTransferForm(forms.ModelForm):
    """Форма операции «Перевод» между счетами."""

    class Meta:
        model = FinanceOperation
        fields = ("account", "account_to", "amount", "description", "date")
        widgets = {
            "date": forms.DateInput(attrs={"type": "date", "class": _input_class()}),
            "amount": forms.NumberInput(attrs={"class": _input_class(), "step": "0.01"}),
            "description": forms.Textarea(attrs={"rows": 2, "class": _input_class()}),
            "account": forms.Select(attrs={"class": _input_class()}),
            "account_to": forms.Select(attrs={"class": _input_class()}),
        }


# ---------- Модуль «Снабжение» ----------


class SupplyRequestForm(forms.ModelForm):
    """Форма заявки на снабжение."""

    class Meta:
        model = SupplyRequest
        fields = ("project", "resource", "required_date", "quantity", "price_plan", "status")
        widgets = {
            "required_date": forms.DateInput(attrs={"type": "date", "class": _input_class()}),
            "quantity": forms.NumberInput(attrs={"class": _input_class(), "step": "0.0001"}),
            "price_plan": forms.NumberInput(attrs={"class": _input_class(), "step": "0.01"}),
            "project": forms.Select(attrs={"class": _input_class()}),
            "resource": forms.Select(attrs={"class": _input_class()}),
            "status": forms.Select(attrs={"class": _input_class()}),
        }


class SupplyOrderForm(forms.ModelForm):
    """Форма заказа (поставщик, статус)."""

    class Meta:
        model = SupplyOrder
        fields = ("supplier", "status")
        widgets = {
            "supplier": forms.TextInput(attrs={"class": _input_class()}),
            "status": forms.Select(attrs={"class": _input_class()}),
        }


class SupplyOrderCreateForm(forms.Form):
    """Создание заказа из выбранных заявок: поставщик + список request id."""

    supplier = forms.CharField(max_length=255, label="Поставщик", widget=forms.TextInput(attrs={"class": _input_class()}))
    request_ids = forms.MultipleChoiceField(
        label="Заявки",
        widget=forms.CheckboxSelectMultiple,
        required=True,
    )

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company:
            # Заявки без заказа, не отменённые
            qs = SupplyRequest.objects.filter(
                company=company,
                status__in=(
                    SupplyRequest.STATUS_DRAFT,
                    SupplyRequest.STATUS_PENDING,
                    SupplyRequest.STATUS_PARTIAL,
                ),
            ).filter(order_item__isnull=True).select_related("resource", "project")
            self.fields["request_ids"].choices = [
                (str(r.id), f"{r.resource.name} — {r.quantity} {r.resource.unit} ({r.project.name})")
                for r in qs
            ]


class ProjectSupplyRequestForm(forms.Form):
    """Создание заявки из проекта (привязка к позиции сметы)."""

    estimate_item = forms.ModelChoiceField(
        label="Ресурс (позиция сметы)",
        queryset=EstimateItem.objects.none(),
    )
    required_date = forms.DateField(
        label="Требуется к дате",
        widget=forms.DateInput(attrs={"type": "date", "class": _input_class()}),
    )
    quantity = forms.DecimalField(
        label="Количество",
        min_value=0,
        max_digits=14,
        decimal_places=4,
        widget=forms.NumberInput(attrs={"class": _input_class(), "step": "0.0001"}),
    )

    def __init__(self, *args, project=None, **kwargs):
        super().__init__(*args, **kwargs)
        if project:
            self.fields["estimate_item"].queryset = (
                EstimateItem.objects.filter(section__project=project)
                .select_related("section")
                .order_by("section__order", "order", "id")
            )


class ProjectSupplyOrderCreateForm(forms.Form):
    supplier = forms.CharField(
        label="Поставщик",
        max_length=255,
        widget=forms.TextInput(attrs={"class": _input_class()}),
    )
    request_ids = forms.MultipleChoiceField(
        label="Заявки",
        widget=forms.CheckboxSelectMultiple,
        required=True,
    )

    def __init__(self, *args, company=None, project=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company and project:
            qs = SupplyRequest.objects.filter(
                company=company,
                project=project,
                status__in=(
                    SupplyRequest.STATUS_DRAFT,
                    SupplyRequest.STATUS_PENDING,
                    SupplyRequest.STATUS_PARTIAL,
                ),
                order_item__isnull=True,
            ).select_related("resource")
            self.fields["request_ids"].choices = [
                (
                    str(r.id),
                    f"{r.resource.name} — {r.quantity} {r.resource.unit} (сумма план {r.total_plan})",
                )
                for r in qs
            ]


class ProjectFinanceIncomeForm(FinanceIncomeForm):
    """Доход в контексте проекта: проект скрыт."""

    def __init__(self, *args, project=None, **kwargs):
        super().__init__(*args, **kwargs)
        if project:
            self.fields["project"].queryset = Project.objects.filter(pk=project.pk)
            self.fields["project"].initial = project.pk
            self.fields["project"].widget = forms.HiddenInput()


class ProjectFinanceExpenseForm(FinanceExpenseForm):
    """Расход в контексте проекта."""

    def __init__(self, *args, project=None, **kwargs):
        super().__init__(*args, **kwargs)
        if project:
            self.fields["project"].queryset = Project.objects.filter(pk=project.pk)
            self.fields["project"].initial = project.pk
            self.fields["project"].widget = forms.HiddenInput()


class ProjectFinanceOperationEditForm(forms.ModelForm):
    """Редактирование строки журнала (баланс пересчитывается в модели)."""

    class Meta:
        model = FinanceOperation
        fields = (
            "account",
            "category",
            "type",
            "amount",
            "description",
            "contractor",
            "date",
            "journal_status",
        )
        widgets = {
            "date": forms.DateInput(attrs={"type": "date", "class": _input_class()}),
            "amount": forms.NumberInput(attrs={"class": _input_class(), "step": "0.01"}),
            "description": forms.Textarea(attrs={"rows": 2, "class": _input_class()}),
            "contractor": forms.TextInput(attrs={"class": _input_class()}),
            "account": forms.Select(attrs={"class": _input_class()}),
            "category": forms.Select(attrs={"class": _input_class()}),
            "type": forms.Select(attrs={"class": _input_class()}),
            "journal_status": forms.Select(attrs={"class": _input_class()}),
        }


class ProjectPaySupplyOrderForm(forms.Form):
    amount = forms.DecimalField(
        label="Сумма оплаты",
        min_value=Decimal("0.01"),
        max_digits=16,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"class": _input_class(), "step": "0.01"}),
    )
    pay_date = forms.DateField(
        label="Дата",
        widget=forms.DateInput(attrs={"type": "date", "class": _input_class()}),
    )


class ProjectPayWorkActForm(forms.Form):
    amount = forms.DecimalField(
        label="Сумма оплаты",
        min_value=Decimal("0.01"),
        max_digits=16,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"class": _input_class(), "step": "0.01"}),
    )
    pay_date = forms.DateField(
        label="Дата",
        widget=forms.DateInput(attrs={"type": "date", "class": _input_class()}),
    )


class WorkActForm(forms.ModelForm):
    """Акт выполненных работ (модуль Документы)."""

    class Meta:
        model = WorkAct
        fields = ("contractor", "work_type", "amount", "act_date", "description")
        widgets = {
            "contractor": forms.TextInput(attrs={"class": _input_class()}),
            "work_type": forms.TextInput(attrs={"class": _input_class()}),
            "amount": forms.NumberInput(attrs={"class": _input_class(), "step": "0.01"}),
            "act_date": forms.DateInput(attrs={"type": "date", "class": _input_class()}),
            "description": forms.Textarea(attrs={"rows": 2, "class": _input_class()}),
        }


class ConstructionWorkReportForm(forms.Form):
    """Отчёт прораба по позиции сметы (модальное окно «Стройка»)."""

    volume = forms.DecimalField(
        label="Выполненный объём",
        min_value=Decimal("0.0001"),
        max_digits=14,
        decimal_places=4,
        widget=forms.NumberInput(
            attrs={"class": _input_class(), "step": "0.0001", "id": "id_construction_volume"}
        ),
    )
    work_date = forms.DateField(
        label="Дата выполнения",
        widget=forms.DateInput(
            attrs={"type": "date", "class": _input_class(), "id": "id_construction_work_date"}
        ),
    )
    comment = forms.CharField(
        label="Комментарий",
        required=False,
        widget=forms.Textarea(
            attrs={"rows": 3, "class": _input_class(), "id": "id_construction_comment"}
        ),
    )


# ---------- Модуль «Склады» ----------


class WarehouseIncomingForm(forms.ModelForm):
    """Поступление на склад (вручную или по заказу)."""

    class Meta:
        model = WarehouseOperation
        fields = ("warehouse", "resource", "quantity", "price", "order")
        widgets = {
            "quantity": forms.NumberInput(attrs={"class": _input_class(), "step": "0.0001"}),
            "price": forms.NumberInput(attrs={"class": _input_class(), "step": "0.01"}),
            "warehouse": forms.Select(attrs={"class": _input_class()}),
            "resource": forms.Select(attrs={"class": _input_class()}),
            "order": forms.Select(attrs={"class": _input_class()}),
        }


class WarehouseOutgoingForm(forms.ModelForm):
    """Списание со склада."""

    class Meta:
        model = WarehouseOperation
        fields = ("warehouse", "resource", "quantity")
        widgets = {
            "quantity": forms.NumberInput(attrs={"class": _input_class(), "step": "0.0001"}),
            "warehouse": forms.Select(attrs={"class": _input_class()}),
            "resource": forms.Select(attrs={"class": _input_class()}),
        }


class WarehouseTransferForm(forms.ModelForm):
    """Перемещение между складами."""

    class Meta:
        model = WarehouseOperation
        fields = ("from_warehouse", "to_warehouse", "resource", "quantity", "price")
        widgets = {
            "quantity": forms.NumberInput(attrs={"class": _input_class(), "step": "0.0001"}),
            "price": forms.NumberInput(attrs={"class": _input_class(), "step": "0.01"}),
            "from_warehouse": forms.Select(attrs={"class": _input_class()}),
            "to_warehouse": forms.Select(attrs={"class": _input_class()}),
            "resource": forms.Select(attrs={"class": _input_class()}),
        }


# ---------- Склады (Material / Stock / StockMovement) ----------


class WarehouseCreateForm(forms.ModelForm):
    """Создание склада."""

    class Meta:
        model = Warehouse
        fields = ("name", "location")
        widgets = {
            "name": forms.TextInput(attrs={"class": _input_class(), "placeholder": "Название"}),
            "location": forms.TextInput(attrs={"class": _input_class(), "placeholder": "Локация"}),
        }


# ---------- Инвентарь (Kanban) ----------


class WarehouseInventoryCreateForm(forms.ModelForm):
    """Добавление инвентаря (название, инв. номер, стоимость, дата, склад, статус, описание, фото)."""

    class Meta:
        model = WarehouseInventoryItem
        fields = (
            "name",
            "inventory_number",
            "purchase_price",
            "purchase_date",
            "warehouse",
            "status",
            "description",
            "image",
        )
        widgets = {
            "name": forms.TextInput(attrs={"class": _input_class(), "placeholder": "Название"}),
            "inventory_number": forms.TextInput(attrs={"class": _input_class(), "placeholder": "Инвентарный номер"}),
            "purchase_price": forms.NumberInput(attrs={"class": _input_class(), "step": "0.01", "min": "0"}),
            "purchase_date": forms.DateInput(attrs={"class": _input_class(), "type": "date"}),
            "warehouse": forms.Select(attrs={"class": _input_class()}),
            "status": forms.Select(attrs={"class": _input_class()}),
            "description": forms.Textarea(attrs={"class": _input_class(), "rows": 3, "placeholder": "Описание"}),
            "image": forms.FileInput(attrs={"class": _input_class(), "accept": "image/*"}),
        }

    def __init__(self, *args, company=None, project=None, default_warehouse=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company:
            from django.db.models import Q
            qs = Warehouse.objects.filter(company=company, is_deleted=False).filter(
                Q(project=project) | Q(project__isnull=True, name="Списано")
            ).order_by("name")
            self.fields["warehouse"].queryset = qs
        if default_warehouse:
            self.initial["warehouse"] = default_warehouse
        from datetime import date as d
        if not self.initial.get("purchase_date"):
            self.initial.setdefault("purchase_date", d.today())


class WarehouseInventoryUpdateForm(forms.ModelForm):
    """Редактирование инвентаря: название, стоимость, дата покупки, статус, будет свободен, описание, фото."""

    class Meta:
        model = WarehouseInventoryItem
        fields = (
            "name",
            "purchase_price",
            "purchase_date",
            "status",
            "available_from",
            "description",
            "image",
        )
        widgets = {
            "name": forms.TextInput(attrs={"class": _input_class(), "placeholder": "Название"}),
            "purchase_price": forms.NumberInput(attrs={"class": _input_class(), "step": "0.01", "min": "0"}),
            "purchase_date": forms.DateInput(attrs={"class": _input_class(), "type": "date"}),
            "status": forms.Select(attrs={"class": _input_class()}),
            "available_from": forms.DateInput(attrs={"class": _input_class(), "type": "date"}),
            "description": forms.Textarea(attrs={"class": _input_class(), "rows": 3}),
            "image": forms.FileInput(attrs={"class": _input_class(), "accept": "image/*"}),
        }


class InventoryTransferForm(forms.Form):
    """Перемещение инвентаря на другой склад."""
    to_warehouse = forms.ModelChoiceField(
        queryset=Warehouse.objects.none(),
        label="Склад назначения",
        widget=forms.Select(attrs={"class": _input_class()}),
    )

    def __init__(self, *args, item=None, **kwargs):
        super().__init__(*args, **kwargs)
        if item:
            qs = Warehouse.objects.filter(company=item.company, is_deleted=False).exclude(
                id=item.warehouse_id
            ).order_by("name")
            self.fields["to_warehouse"].queryset = qs


class MaterialCreateForm(forms.ModelForm):
    """Добавление материала в справочник компании."""

    class Meta:
        model = Material
        fields = ("name", "unit", "category")
        widgets = {
            "name": forms.TextInput(attrs={"class": _input_class(), "placeholder": "Название"}),
            "unit": forms.TextInput(attrs={"class": _input_class(), "placeholder": "ед. изм."}),
            "category": forms.Select(attrs={"class": _input_class()}),
        }


class StockIncomingForm(forms.Form):
    """Поступление на склад (Material + Stock)."""
    material = forms.ModelChoiceField(queryset=Material.objects.none(), label="Материал", widget=forms.Select(attrs={"class": _input_class()}))
    warehouse = forms.ModelChoiceField(queryset=Warehouse.objects.none(), label="Склад", widget=forms.Select(attrs={"class": _input_class()}))
    quantity = forms.DecimalField(max_digits=14, decimal_places=4, min_value=0, widget=forms.NumberInput(attrs={"class": _input_class(), "step": "0.0001"}))
    price = forms.DecimalField(max_digits=14, decimal_places=2, min_value=0, widget=forms.NumberInput(attrs={"class": _input_class(), "step": "0.01"}))
    date = forms.DateField(widget=forms.DateInput(attrs={"class": _input_class(), "type": "date"}))
    comment = forms.CharField(required=False, max_length=500, widget=forms.TextInput(attrs={"class": _input_class(), "placeholder": "Комментарий"}))

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company:
            self.fields["material"].queryset = company.materials.all().order_by("category", "name")
            self.fields["warehouse"].queryset = company.warehouses.all().order_by("name")
        from datetime import date as d
        if not self.initial.get("date"):
            self.initial.setdefault("date", d.today())


class StockWriteoffForm(forms.Form):
    """Списание со склада (на объект или просто списание)."""
    material = forms.ModelChoiceField(queryset=Material.objects.none(), label="Материал", widget=forms.Select(attrs={"class": _input_class()}))
    warehouse = forms.ModelChoiceField(queryset=Warehouse.objects.none(), label="Склад", widget=forms.Select(attrs={"class": _input_class()}))
    quantity = forms.DecimalField(max_digits=14, decimal_places=4, min_value=0, widget=forms.NumberInput(attrs={"class": _input_class(), "step": "0.0001"}))
    project = forms.ModelChoiceField(queryset=Project.objects.none(), label="Проект (опционально)", required=False, widget=forms.Select(attrs={"class": _input_class()}))
    date = forms.DateField(widget=forms.DateInput(attrs={"class": _input_class(), "type": "date"}))
    comment = forms.CharField(required=False, max_length=500, widget=forms.TextInput(attrs={"class": _input_class(), "placeholder": "Комментарий"}))

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company:
            self.fields["material"].queryset = company.materials.all().order_by("category", "name")
            self.fields["warehouse"].queryset = company.warehouses.all().order_by("name")
            self.fields["project"].queryset = company.projects.all().order_by("name")


class StockTransferForm(forms.Form):
    """Перемещение между складами."""
    material = forms.ModelChoiceField(queryset=Material.objects.none(), label="Материал", widget=forms.Select(attrs={"class": _input_class()}))
    warehouse_from = forms.ModelChoiceField(queryset=Warehouse.objects.none(), label="Склад отправитель", widget=forms.Select(attrs={"class": _input_class()}))
    warehouse_to = forms.ModelChoiceField(queryset=Warehouse.objects.none(), label="Склад получатель", widget=forms.Select(attrs={"class": _input_class()}))
    quantity = forms.DecimalField(max_digits=14, decimal_places=4, min_value=0, widget=forms.NumberInput(attrs={"class": _input_class(), "step": "0.0001"}))
    date = forms.DateField(widget=forms.DateInput(attrs={"class": _input_class(), "type": "date"}))
    comment = forms.CharField(required=False, max_length=500, widget=forms.TextInput(attrs={"class": _input_class(), "placeholder": "Комментарий"}))

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company:
            self.fields["material"].queryset = company.materials.all().order_by("category", "name")
            self.fields["warehouse_from"].queryset = company.warehouses.all().order_by("name")
            self.fields["warehouse_to"].queryset = company.warehouses.all().order_by("name")

    def clean(self):
        data = super().clean()
        if data.get("warehouse_from") and data.get("warehouse_to") and data["warehouse_from"] == data["warehouse_to"]:
            raise forms.ValidationError("Выберите разные склады.")
        return data


# ---------- Настройки → Права доступа ----------


class AddCompanyUserForm(forms.Form):
    """Форма добавления пользователя в компанию (модальное окно)."""

    email = forms.EmailField(label="Email", required=True, widget=forms.EmailInput(attrs={"class": _input_class()}))
    role = forms.ModelChoiceField(
        label="Роль в компании",
        queryset=CompanyRole.objects.none(),
        required=True,
        widget=forms.Select(attrs={"class": _input_class()}),
    )
    projects = forms.MultipleChoiceField(
        label="Проекты",
        required=False,
        widget=forms.CheckboxSelectMultiple,
        choices=[],
    )
    role_in_project = forms.ChoiceField(
        label="Роль в проекте",
        choices=ProjectAccess.ROLE_CHOICES,
        initial=ProjectAccess.ROLE_VIEWER,
        widget=forms.Select(attrs={"class": _input_class()}),
    )
    auto_add_to_new_projects = forms.BooleanField(
        label="Автоматически добавлять в новые проекты",
        required=False,
        initial=False,
    )

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company:
            self.fields["role"].queryset = company.roles.all().order_by("is_system", "name")
            self.fields["projects"].choices = [
                (str(p.id), p.name) for p in company.projects.all().order_by("name")
            ]


class EditCompanyUserForm(forms.ModelForm):
    """Форма редактирования пользователя компании."""

    class Meta:
        model = CompanyUser
        fields = ("role", "is_active", "auto_add_to_new_projects")
        widgets = {
            "role": forms.Select(attrs={"class": _input_class()}),
        }

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company:
            self.fields["role"].queryset = company.roles.all().order_by("is_system", "name")


# ---------- Смета проекта ----------


class EstimateSectionForm(forms.ModelForm):
    class Meta:
        model = EstimateSection
        fields = ("name", "order")
        widgets = {
            "name": forms.TextInput(attrs={"class": _input_class(), "placeholder": "Название раздела"}),
            "order": forms.NumberInput(attrs={"class": _input_class(), "min": 0}),
        }


def _inline_input():
    return "w-full min-w-0 rounded border border-slate-200 px-2 py-1 text-sm focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"


class EstimateItemForm(forms.ModelForm):
    class Meta:
        model = EstimateItem
        fields = ("name", "type", "unit", "quantity", "cost_price", "markup_percent", "order")
        widgets = {
            "name": forms.TextInput(attrs={"class": _input_class(), "placeholder": "Название"}),
            "type": forms.Select(attrs={"class": _input_class()}),
            "unit": forms.TextInput(attrs={"class": _input_class(), "placeholder": "ед. изм."}),
            "quantity": forms.NumberInput(attrs={"class": _input_class(), "step": "any", "min": "0"}),
            "cost_price": forms.NumberInput(attrs={"class": _input_class(), "step": "0.01", "min": "0"}),
            "markup_percent": forms.NumberInput(
                attrs={"class": _input_class(), "step": "0.01", "min": "0"},
            ),
            "order": forms.NumberInput(attrs={"class": _input_class(), "min": 0}),
        }


class EstimateItemInlineForm(forms.ModelForm):
    """Редактирование позиции прямо в таблице сметы (без перехода на отдельную страницу)."""

    class Meta:
        model = EstimateItem
        fields = ("name", "type", "unit", "quantity", "cost_price", "markup_percent")
        widgets = {
            "name": forms.TextInput(attrs={"class": _inline_input(), "placeholder": "Наименование"}),
            "type": forms.Select(attrs={"class": _inline_input()}),
            "unit": forms.TextInput(attrs={"class": _inline_input(), "placeholder": "ед."}),
            "quantity": forms.NumberInput(attrs={"class": _inline_input(), "step": "any", "min": "0"}),
            "cost_price": forms.NumberInput(attrs={"class": _inline_input(), "step": "0.01", "min": "0"}),
            "markup_percent": forms.NumberInput(
                attrs={"class": _inline_input(), "step": "0.01", "min": "0"},
            ),
        }


class ProjectSchedulePhaseForm(forms.ModelForm):
    class Meta:
        model = ProjectSchedulePhase
        fields = (
            "name",
            "estimate_section",
            "start_date",
            "end_date",
            "status",
            "progress",
            "assignee",
            "predecessor",
        )
        widgets = {
            "name": forms.TextInput(attrs={"class": _input_class(), "placeholder": "Название этапа"}),
            "estimate_section": forms.Select(attrs={"class": _input_class()}),
            "start_date": forms.DateInput(attrs={"type": "date", "class": _input_class()}),
            "end_date": forms.DateInput(attrs={"type": "date", "class": _input_class()}),
            "status": forms.Select(attrs={"class": _input_class()}),
            "progress": forms.NumberInput(
                attrs={"class": _input_class(), "min": 0, "max": 100},
            ),
            "assignee": forms.Select(attrs={"class": _input_class()}),
            "predecessor": forms.Select(attrs={"class": _input_class()}),
        }

    def __init__(self, *args, project=None, **kwargs):
        super().__init__(*args, **kwargs)
        if project:
            self.fields["estimate_section"].queryset = EstimateSection.objects.filter(
                project=project
            ).order_by("order", "id")
            self.fields["estimate_section"].required = False
            pred_qs = ProjectSchedulePhase.objects.filter(project=project)
            if self.instance.pk:
                pred_qs = pred_qs.exclude(pk=self.instance.pk)
            self.fields["predecessor"].queryset = pred_qs.order_by("order", "id")
            self.fields["predecessor"].required = False
            self.fields["assignee"].queryset = User.objects.filter(
                company_users__company=project.company
            ).distinct().order_by("username")
            self.fields["assignee"].required = False

