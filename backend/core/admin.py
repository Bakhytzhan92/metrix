from django.contrib import admin

from .models import (
    Company,
    CompanyRole,
    CompanyUser,
    ProjectAccess,
    Project,
    UploadedDocument,
    Task,
    Finance,
    InventoryItem,
    GeneratedContent,
    Account,
    FinanceCategory,
    FinanceOperation,
    Resource,
    SupplyRequest,
    SupplyOrder,
    SupplyOrderItem,
    Warehouse,
    StockItem,
    WarehouseOperation,
    EstimateSection,
    EstimateItem,
    ConstructionWorkLog,
    ConstructionWorkPhoto,
    WorkAct,
    ProjectSchedulePhase,
    Material,
    Stock,
    StockMovement,
    WarehouseInventoryItem,
    InventoryTransfer,
    InventoryLog,
)


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("name", "subscription_plan", "subscription_expires_at", "owner")
    search_fields = ("name",)


@admin.register(CompanyRole)
class CompanyRoleAdmin(admin.ModelAdmin):
    list_display = ("name", "company", "slug", "is_system")
    list_filter = ("company", "is_system")


@admin.register(CompanyUser)
class CompanyUserAdmin(admin.ModelAdmin):
    list_display = ("user", "company", "role", "is_active", "auto_add_to_new_projects")
    list_filter = ("company", "is_active")


@admin.register(ProjectAccess)
class ProjectAccessAdmin(admin.ModelAdmin):
    list_display = ("company_user", "project", "role_in_project")
    list_filter = ("project__company",)


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("name", "company", "status", "start_date", "end_date", "created_at")
    list_filter = ("status", "company")
    search_fields = ("name",)


@admin.register(UploadedDocument)
class UploadedDocumentAdmin(admin.ModelAdmin):
    list_display = ("id", "project", "status", "project_type", "uploaded_at", "uploaded_by")
    list_filter = ("status", "project_type")
    search_fields = ("project__name",)
    readonly_fields = ("uploaded_at", "parsed_text", "ai_result")


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("title", "project", "assigned_to", "status", "priority", "due_date", "created_at")
    list_filter = ("status", "priority", "project")
    search_fields = ("title", "description")


@admin.register(Finance)
class FinanceAdmin(admin.ModelAdmin):
    list_display = ("project", "amount", "category", "date")
    list_filter = ("category", "project")


@admin.register(InventoryItem)
class InventoryItemAdmin(admin.ModelAdmin):
    list_display = ("name", "project", "quantity", "unit")


@admin.register(GeneratedContent)
class GeneratedContentAdmin(admin.ModelAdmin):
    list_display = ("user", "created_at")
    readonly_fields = ("created_at",)


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ("name", "company", "balance", "currency")
    list_filter = ("company",)


@admin.register(FinanceCategory)
class FinanceCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "company", "type", "pnl_group", "cashflow_group")
    list_filter = ("company", "type", "pnl_group", "cashflow_group")


@admin.register(FinanceOperation)
class FinanceOperationAdmin(admin.ModelAdmin):
    list_display = (
        "date",
        "company",
        "type",
        "account",
        "amount",
        "category",
        "project",
        "basis",
        "journal_status",
        "deleted_at",
    )
    list_filter = ("company", "type", "date", "basis", "journal_status")
    readonly_fields = ("created_at",)

    def get_queryset(self, request):
        return FinanceOperation.all_objects.all()


@admin.register(WorkAct)
class WorkActAdmin(admin.ModelAdmin):
    list_display = (
        "contractor",
        "project",
        "amount",
        "act_date",
        "payment_status",
        "paid_amount",
    )
    list_filter = ("company", "payment_status", "project")
    search_fields = ("contractor", "work_type")


@admin.register(Resource)
class ResourceAdmin(admin.ModelAdmin):
    list_display = ("name", "company", "type", "unit")
    list_filter = ("company", "type")


@admin.register(SupplyRequest)
class SupplyRequestAdmin(admin.ModelAdmin):
    list_display = ("resource", "project", "required_date", "quantity", "price_plan", "total_plan", "status")
    list_filter = ("company", "status", "resource__type")


@admin.register(SupplyOrder)
class SupplyOrderAdmin(admin.ModelAdmin):
    list_display = ("supplier", "company", "status", "created_at")
    list_filter = ("company", "status")


@admin.register(SupplyOrderItem)
class SupplyOrderItemAdmin(admin.ModelAdmin):
    list_display = ("order", "request", "quantity", "price_fact", "total_fact")


@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ("name", "company", "location", "project", "created_at")
    list_filter = ("company",)


@admin.register(Material)
class MaterialAdmin(admin.ModelAdmin):
    list_display = ("name", "company", "unit", "category")
    list_filter = ("company", "category")


@admin.register(Stock)
class StockAdmin(admin.ModelAdmin):
    list_display = ("warehouse", "material", "quantity", "price_avg")
    list_filter = ("warehouse__company",)


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ("id", "material", "movement_type", "quantity", "warehouse_from", "warehouse_to", "project", "date", "total")
    list_filter = ("movement_type", "date")
    readonly_fields = ("total", "created_at")


@admin.register(WarehouseInventoryItem)
class WarehouseInventoryItemAdmin(admin.ModelAdmin):
    list_display = ("name", "warehouse", "status", "inventory_number", "purchase_price", "purchase_date")
    list_filter = ("company", "warehouse", "status")


@admin.register(InventoryTransfer)
class InventoryTransferAdmin(admin.ModelAdmin):
    list_display = ("item", "from_warehouse", "to_warehouse", "date", "user")
    list_filter = ("to_warehouse__company",)


@admin.register(InventoryLog)
class InventoryLogAdmin(admin.ModelAdmin):
    list_display = ("item", "action", "description", "created_at", "user")
    list_filter = ("action",)


@admin.register(StockItem)
class StockItemAdmin(admin.ModelAdmin):
    list_display = ("warehouse", "resource", "quantity", "price_avg", "total_sum", "updated_at")
    list_filter = ("warehouse__company",)


@admin.register(WarehouseOperation)
class WarehouseOperationAdmin(admin.ModelAdmin):
    list_display = ("id", "company", "operation_type", "warehouse", "resource", "quantity", "total", "order", "created_at")
    list_filter = ("company", "operation_type")
    readonly_fields = ("created_at", "total")


@admin.register(EstimateSection)
class EstimateSectionAdmin(admin.ModelAdmin):
    list_display = ("name", "project", "order")
    list_filter = ("project__company",)
    ordering = ("project", "order", "id")


@admin.register(ProjectSchedulePhase)
class ProjectSchedulePhaseAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "project",
        "start_date",
        "end_date",
        "status",
        "progress",
        "assignee",
        "estimate_section",
    )
    list_filter = ("status", "project")
    search_fields = ("name",)


@admin.register(EstimateItem)
class EstimateItemAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "section",
        "type",
        "unit",
        "quantity",
        "cost_price",
        "markup_percent",
        "sell_price",
        "total_cost",
        "total_price",
    )
    list_filter = ("section__project", "type")
    ordering = ("section", "order", "id")
    readonly_fields = ("total_cost", "total_price", "created_at")


@admin.register(ConstructionWorkLog)
class ConstructionWorkLogAdmin(admin.ModelAdmin):
    list_display = ("work_date", "estimate_item", "volume", "created_by", "created_at")
    list_filter = ("work_date",)
    search_fields = ("comment", "estimate_item__name")
    raw_id_fields = ("estimate_item",)


@admin.register(ConstructionWorkPhoto)
class ConstructionWorkPhotoAdmin(admin.ModelAdmin):
    list_display = ("work_log", "caption", "created_at")
    raw_id_fields = ("work_log",)

