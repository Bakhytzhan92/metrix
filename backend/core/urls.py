from django.urls import include, path

from . import ai_api
from . import construction_docs_api
from . import estimate_pdf_views
from . import fuel_project_api
from . import inventory_api
from . import materials_project_api
from . import timesheet_project_api
from . import views
from .urls_superadmin import api_urlpatterns as superadmin_api_urls
from .urls_superadmin import urlpatterns as superadmin_page_urls

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("projects/add/", views.project_create, name="project_create"),
    path("projects/<int:pk>/", views.project_overview, name="project_detail"),
    path("projects/<int:pk>/analytics/", views.project_analytics, name="project_analytics"),
    path("projects/<int:pk>/estimate/", views.project_estimate, name="project_estimate"),
    path("projects/<int:pk>/estimate/vat/", views.estimate_vat_toggle, name="estimate_vat_toggle"),
    path("projects/<int:pk>/estimate/section/add/", views.estimate_section_add, name="estimate_section_add"),
    path("projects/<int:pk>/estimate/section/<int:section_id>/edit/", views.estimate_section_edit, name="estimate_section_edit"),
    path("projects/<int:pk>/estimate/section/<int:section_id>/inline/", views.estimate_section_inline, name="estimate_section_inline"),
    path("projects/<int:pk>/estimate/section/<int:section_id>/delete/", views.estimate_section_delete, name="estimate_section_delete"),
    path(
        "projects/<int:pk>/estimate/sections/delete-all/",
        views.estimate_sections_delete_all,
        name="estimate_sections_delete_all",
    ),
    path("projects/<int:pk>/estimate/section/<int:section_id>/item/add/", views.estimate_item_add, name="estimate_item_add"),
    path("projects/<int:pk>/estimate/section/<int:section_id>/item/quick-add/", views.estimate_item_quick_add, name="estimate_item_quick_add"),
    path("projects/<int:pk>/estimate/section/<int:section_id>/item/<int:item_id>/edit/", views.estimate_item_edit, name="estimate_item_edit"),
    path("projects/<int:pk>/estimate/section/<int:section_id>/item/<int:item_id>/inline/", views.estimate_item_inline, name="estimate_item_inline"),
    path("projects/<int:pk>/estimate/section/<int:section_id>/item/<int:item_id>/delete/", views.estimate_item_delete, name="estimate_item_delete"),
    path("projects/<int:pk>/estimate/import/", views.estimate_import, name="estimate_import"),
    path("projects/<int:pk>/estimate/export/", views.estimate_export, name="estimate_export"),
    path("projects/<int:pk>/schedule/", views.project_schedule, name="project_schedule"),
    path(
        "projects/<int:pk>/schedule/virtual-data/",
        views.project_schedule_virtual_data,
        name="project_schedule_virtual_data",
    ),
    path(
        "projects/<int:pk>/schedule/item/<int:item_id>/api/",
        views.schedule_item_api,
        name="schedule_item_api",
    ),
    path("projects/<int:pk>/supply/", views.project_supply, name="project_supply"),
    path("projects/<int:pk>/timesheet/", views.project_timesheet, name="project_timesheet"),
    path(
        "projects/<int:pk>/supply/request/create/",
        views.project_supply_request_create,
        name="project_supply_request_create",
    ),
    path(
        "projects/<int:pk>/supply/order/create/",
        views.project_supply_order_create,
        name="project_supply_order_create",
    ),
    path(
        "projects/<int:pk>/supply/request/<int:req_id>/api/",
        views.project_supply_request_api,
        name="project_supply_request_api",
    ),
    path(
        "projects/<int:pk>/supply/order/<int:order_id>/payment/",
        views.project_supply_order_payment,
        name="project_supply_order_payment",
    ),
    path("projects/<int:pk>/finance/", views.project_finance_section, name="project_finance_section"),
    path(
        "projects/<int:pk>/finance/export/",
        views.project_finance_export_journal,
        name="project_finance_export_journal",
    ),
    path(
        "projects/<int:pk>/finance/income/",
        views.project_finance_income_create,
        name="project_finance_income_create",
    ),
    path(
        "projects/<int:pk>/finance/expense/",
        views.project_finance_expense_create,
        name="project_finance_expense_create",
    ),
    path(
        "projects/<int:pk>/finance/operation/<int:op_id>/edit/",
        views.project_finance_operation_edit,
        name="project_finance_operation_edit",
    ),
    path(
        "projects/<int:pk>/finance/operation/<int:op_id>/delete/",
        views.project_finance_operation_soft_delete,
        name="project_finance_operation_soft_delete",
    ),
    path(
        "projects/<int:pk>/finance/pay-supply/<int:order_id>/",
        views.project_finance_pay_supply_order,
        name="project_finance_pay_supply_order",
    ),
    path(
        "projects/<int:pk>/finance/pay-act/<int:act_id>/",
        views.project_finance_pay_work_act,
        name="project_finance_pay_work_act",
    ),
    path(
        "projects/<int:pk>/supply/order/<int:order_id>/submit-payment/",
        views.project_supply_order_submit_payment,
        name="project_supply_order_submit_payment",
    ),
    path(
        "projects/<int:pk>/documents/act/create/",
        views.project_work_act_create,
        name="project_work_act_create",
    ),
    path(
        "projects/<int:pk>/documents/act/<int:act_id>/submit-payment/",
        views.project_work_act_submit_payment,
        name="project_work_act_submit_payment",
    ),
    path("projects/<int:pk>/construction/", views.project_construction, name="project_construction"),
    path(
        "projects/<int:pk>/construction/log/",
        views.project_construction_log,
        name="project_construction_log",
    ),
    path(
        "projects/<int:pk>/construction/journal/export/",
        views.project_construction_journal_export,
        name="project_construction_journal_export",
    ),
    path(
        "projects/<int:pk>/construction/journal/print/",
        views.project_construction_journal_print,
        name="project_construction_journal_print",
    ),
    path("projects/<int:pk>/warehouses/", views.project_warehouses, name="project_warehouses"),
    path("projects/<int:pk>/warehouses/create/", views.project_warehouse_create, name="project_warehouse_create"),
    path(
        "projects/<int:pk>/warehouses/<int:warehouse_id>/delete/",
        views.project_warehouse_delete,
        name="project_warehouse_delete",
    ),
    path("projects/<int:pk>/warehouses/inventory/create/", views.project_inventory_create, name="project_inventory_create"),
    path("projects/<int:pk>/warehouses/inventory/<int:item_id>/update/", views.project_inventory_update, name="project_inventory_update"),
    path("projects/<int:pk>/warehouses/inventory/<int:item_id>/transfer/", views.project_inventory_transfer, name="project_inventory_transfer"),
    path(
        "projects/<int:pk>/warehouses/inventory/<int:item_id>/delete/",
        views.project_warehouse_inventory_delete,
        name="project_warehouse_inventory_delete",
    ),
    path(
        "api/project/<int:pk>/materials/meta/",
        materials_project_api.api_project_materials_meta,
        name="api_project_materials_meta",
    ),
    path(
        "api/project/<int:pk>/materials/catalog/",
        materials_project_api.api_project_materials_catalog,
        name="api_project_materials_catalog",
    ),
    path(
        "api/project/<int:pk>/materials/stocks/<int:stock_id>/",
        materials_project_api.api_project_materials_stock_detail,
        name="api_project_materials_stock_detail",
    ),
    path(
        "api/project/<int:pk>/materials/stocks/",
        materials_project_api.api_project_materials_stocks,
        name="api_project_materials_stocks",
    ),
    path(
        "api/project/<int:pk>/materials/history/",
        materials_project_api.api_project_materials_history,
        name="api_project_materials_history",
    ),
    path(
        "api/project/<int:pk>/materials/create/",
        materials_project_api.api_project_materials_create,
        name="api_project_materials_create",
    ),
    path(
        "api/project/<int:pk>/materials/incoming/",
        materials_project_api.api_project_materials_incoming,
        name="api_project_materials_incoming",
    ),
    path(
        "api/project/<int:pk>/materials/outgoing/",
        materials_project_api.api_project_materials_outgoing,
        name="api_project_materials_outgoing",
    ),
    path(
        "api/project/<int:pk>/materials/transfer/",
        materials_project_api.api_project_materials_transfer,
        name="api_project_materials_transfer",
    ),
    path(
        "api/project/<int:pk>/materials/writeoff/",
        materials_project_api.api_project_materials_writeoff,
        name="api_project_materials_writeoff",
    ),
    path(
        "api/project/<int:pk>/gsm/meta/",
        fuel_project_api.api_project_gsm_meta,
        name="api_project_gsm_meta",
    ),
    path(
        "api/project/<int:pk>/gsm/stocks/",
        fuel_project_api.api_project_gsm_stocks,
        name="api_project_gsm_stocks",
    ),
    path(
        "api/project/<int:pk>/gsm/history/",
        fuel_project_api.api_project_gsm_history,
        name="api_project_gsm_history",
    ),
    path(
        "api/project/<int:pk>/gsm/analytics/",
        fuel_project_api.api_project_gsm_analytics,
        name="api_project_gsm_analytics",
    ),
    path(
        "api/project/<int:pk>/gsm/timeseries/",
        fuel_project_api.api_project_gsm_timeseries,
        name="api_project_gsm_timeseries",
    ),
    path(
        "api/project/<int:pk>/gsm/incoming/",
        fuel_project_api.api_project_gsm_incoming,
        name="api_project_gsm_incoming",
    ),
    path(
        "api/project/<int:pk>/gsm/issue/",
        fuel_project_api.api_project_gsm_issue,
        name="api_project_gsm_issue",
    ),
    path(
        "api/project/<int:pk>/gsm/writeoff/",
        fuel_project_api.api_project_gsm_writeoff,
        name="api_project_gsm_writeoff",
    ),
    path(
        "api/project/<int:pk>/gsm/fuel-type/create/",
        fuel_project_api.api_project_gsm_fuel_type_create,
        name="api_project_gsm_fuel_type_create",
    ),
    path(
        "api/project/<int:pk>/timesheet/",
        timesheet_project_api.api_project_timesheet_month,
        name="api_project_timesheet_month",
    ),
    path(
        "api/project/<int:pk>/timesheet/cell/",
        timesheet_project_api.api_project_timesheet_cell,
        name="api_project_timesheet_cell",
    ),
    path(
        "api/project/<int:pk>/timesheet/bulk/",
        timesheet_project_api.api_project_timesheet_bulk,
        name="api_project_timesheet_bulk",
    ),
    path(
        "api/project/<int:pk>/timesheet/export/",
        timesheet_project_api.api_project_timesheet_export,
        name="api_project_timesheet_export",
    ),
    path(
        "api/project/<int:pk>/timesheet/import-employees/",
        timesheet_project_api.api_project_timesheet_import_employees,
        name="api_project_timesheet_import_employees",
    ),
    path(
        "api/project/<int:pk>/timesheet/logs/",
        timesheet_project_api.api_project_timesheet_logs,
        name="api_project_timesheet_logs",
    ),
    path(
        "api/project/<int:pk>/timesheet/employees/",
        timesheet_project_api.api_project_timesheet_employee_create,
        name="api_project_timesheet_employee_create",
    ),
    path(
        "api/project/<int:pk>/timesheet/employees/<int:employee_id>/",
        timesheet_project_api.api_project_timesheet_employee_update,
        name="api_project_timesheet_employee_update",
    ),
    path(
        "api/project/<int:pk>/timesheet/employees/<int:employee_id>/remove/",
        timesheet_project_api.api_project_timesheet_employee_remove,
        name="api_project_timesheet_employee_remove",
    ),
    path("projects/<int:pk>/documents/", views.project_documents, name="project_documents"),
    path(
        "projects/<int:pk>/documents/api/meta/",
        construction_docs_api.api_construction_meta,
        name="api_construction_docs_meta",
    ),
    path(
        "projects/<int:pk>/documents/api/folders/",
        construction_docs_api.api_construction_folders_tree,
        name="api_construction_folders_tree",
    ),
    path(
        "projects/<int:pk>/documents/api/folder/create/",
        construction_docs_api.api_construction_folder_create,
        name="api_construction_folder_create",
    ),
    path(
        "projects/<int:pk>/documents/api/files/",
        construction_docs_api.api_construction_files_list,
        name="api_construction_files_list",
    ),
    path(
        "projects/<int:pk>/documents/api/files/upload/",
        construction_docs_api.api_construction_files_upload,
        name="api_construction_files_upload",
    ),
    path(
        "projects/<int:pk>/documents/api/files/<int:file_id>/",
        construction_docs_api.api_construction_file_detail,
        name="api_construction_file_detail",
    ),
    path("projects/<int:pk>/ai/", ai_api.project_ai_import, name="project_ai_import"),
    path("projects/<int:pk>/legacy/", views.project_detail, name="project_legacy"),
    path("projects/<int:pk>/edit/", views.project_edit, name="project_edit"),
    path("projects/<int:pk>/delete/", views.project_delete, name="project_delete"),
    # Модуль «Задачи» (страница /tasks/)
    path("tasks/", views.task_list, name="task_list"),
    path("tasks/create/", views.task_create, name="task_create"),
    path("tasks/<int:pk>/edit/", views.task_edit, name="task_edit"),
    path("tasks/<int:pk>/status/", views.task_status, name="task_status"),
    path("tasks/<int:pk>/delete/", views.delete_task, name="task_delete"),
    path("finances/<int:pk>/delete/", views.delete_finance, name="finance_delete"),
    # Модуль «Финансы»: журнал операций
    path("finance/", views.finance_dashboard, name="finance_dashboard"),
    path("finance/income/", views.finance_income, name="finance_income"),
    path("finance/expense/", views.finance_expense, name="finance_expense"),
    path("finance/transfer/", views.finance_transfer, name="finance_transfer"),
    path("finance/operation/<int:pk>/delete/", views.finance_operation_delete, name="finance_operation_delete"),
    # Модуль «Снабжение»
    path("supply/", views.supply_dashboard, name="supply_dashboard"),
    path("supply/request/create/", views.supply_request_create, name="supply_request_create"),
    path("supply/order/create/", views.supply_order_create, name="supply_order_create"),
    path("supply/order/<int:pk>/", views.supply_order_detail, name="supply_order_detail"),
    # Модуль «Склады»
    path("warehouses/", views.warehouse_list, name="warehouses_dashboard"),
    path("warehouses/create/", views.warehouse_create, name="warehouse_create"),
    path("warehouses/<int:pk>/", views.warehouse_detail, name="warehouse_detail"),
    path("warehouses/incoming/", views.warehouses_incoming, name="warehouses_incoming"),
    path("warehouses/stock/incoming/", views.stock_incoming, name="stock_incoming"),
    path("warehouses/stock/writeoff/", views.stock_writeoff, name="stock_writeoff"),
    path("warehouses/stock/transfer/", views.stock_transfer, name="stock_transfer"),
    path("warehouses/materials/create/", views.material_create, name="material_create"),
    path("equipment/", views.company_equipment_list, name="company_equipment_list"),
    path("equipment/add/", views.company_equipment_create, name="company_equipment_create"),
    path("equipment/<int:pk>/", views.company_equipment_detail, name="company_equipment_detail"),
    path("equipment/<int:pk>/edit/", views.company_equipment_edit, name="company_equipment_edit"),
    path(
        "equipment/<int:pk>/document/",
        views.company_equipment_document_add,
        name="company_equipment_document_add",
    ),
    path(
        "equipment/qr/<uuid:token>/",
        views.company_equipment_qr_card,
        name="company_equipment_qr_card",
    ),
    path("warehouses/outgoing/", views.warehouses_outgoing, name="warehouses_outgoing"),
    path("warehouses/transfer/", views.warehouses_transfer, name="warehouses_transfer"),
    path("warehouses/inventory/", views.warehouse_inventory_erp, name="warehouse_inventory_erp"),
    path("api/inventory/meta/", inventory_api.api_inventory_meta),
    path("api/inventory/warehouses/summary/", inventory_api.api_inventory_warehouse_summary),
    path("api/inventory/warehouses/", inventory_api.api_inventory_warehouses),
    path("api/inventory/warehouses/<int:pk>/", inventory_api.api_inventory_warehouse_detail),
    path("api/inventory/items/", inventory_api.api_inventory_items),
    path("api/inventory/items/<int:pk>/", inventory_api.api_inventory_item_detail),
    path("api/inventory/items/<int:pk>/move/", inventory_api.api_inventory_item_move),
    path("api/inventory/items/<int:pk>/issue/", inventory_api.api_inventory_item_issue),
    path("api/inventory/items/<int:pk>/return/", inventory_api.api_inventory_item_return),
    path("api/inventory/items/<int:pk>/repair/", inventory_api.api_inventory_item_repair),
    path("api/inventory/items/<int:pk>/lost/", inventory_api.api_inventory_item_lost),
    path("api/inventory/items/<int:pk>/writeoff/", inventory_api.api_inventory_item_writeoff),
    path("api/inventory/items/<int:pk>/qr/", inventory_api.api_inventory_item_qr),
    path("api/inventory/history/", inventory_api.api_inventory_history),
    # Модуль «Отчёты»
    path("reports/", views.reports_index, name="reports_index"),
    path("reports/pnl/", views.reports_pnl, name="reports_pnl"),
    path("reports/cashflow/", views.reports_cashflow, name="reports_cashflow"),
    path("reports/project/<int:id>/", views.reports_project, name="reports_project"),
    path(
        "inventory/<int:pk>/delete/",
        views.delete_inventory_item,
        name="inventory_delete",
    ),
    path("company/settings/", views.company_settings, name="company_settings"),
    # Умный импорт PDF + ИИ (API)
    path("api/upload-pdf/", ai_api.api_upload_pdf, name="api_upload_pdf"),
    path("api/document/<int:doc_id>/", ai_api.api_document_detail, name="api_document_detail"),
    path(
        "api/document/<int:doc_id>/apply/",
        ai_api.api_document_apply,
        name="api_document_apply",
    ),
    path(
        "api/estimates/import-pdf/",
        estimate_pdf_views.api_estimate_import_pdf,
        name="api_estimate_import_pdf",
    ),
    path(
        "api/estimates/import-pdf/apply/",
        estimate_pdf_views.api_estimate_import_pdf_apply,
        name="api_estimate_import_pdf_apply",
    ),
    path(
        "api/estimates/import-pdf/apply-file/",
        estimate_pdf_views.api_estimate_import_pdf_apply_file,
        name="api_estimate_import_pdf_apply_file",
    ),
    # Настройки → Права доступа
    path("settings/access/", views.settings_access, name="settings_access"),
    path("settings/access/add/", views.settings_access_add_user, name="settings_access_add_user"),
    path("settings/access/<int:pk>/edit/", views.settings_access_edit, name="settings_access_edit"),
    path("settings/access/<int:pk>/delete/", views.settings_access_delete, name="settings_access_delete"),
    path(
        "superadmin/",
        include(
            (
                superadmin_page_urls,
                "superadmin",
            ),
        ),
    ),
    path(
        "api/superadmin/",
        include(
            (
                superadmin_api_urls,
                "api_superadmin",
            ),
        ),
    ),
]

