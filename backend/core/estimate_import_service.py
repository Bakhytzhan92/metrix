"""
Импорт сметы из Excel (.xlsx, .xls).
Колонки: 1 — № п/п, 3 — наименование, 4 — ед. изм., 5 — количество.
Разделы и позиции — как в локальной смете АВС; PDF-импорт не затрагивается.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.db import transaction
from django.db.models import Max

from .models import (
    ESTIMATE_ITEM_NAME_MAX_LENGTH,
    EstimateItem,
    EstimateSection,
    Project,
)
from .services.excel_estimate_parser import (
    normalize_estimate_name,
    normalize_excel_unit,
    parse_excel_estimate,
)


def _section_order_from_list_no(list_no: str, fallback: int) -> int:
    n = (list_no or "").strip()
    if n.isdigit():
        return int(n)
    return fallback


def import_estimate_from_excel(project: Project, file) -> dict[str, Any]:
    """
    Импортирует смету из Excel.
    Возвращает статистику: sections_created, items_created, skipped, errors.
    """
    parsed = parse_excel_estimate(file)
    errors: list[str] = list(parsed.errors)

    if not parsed.rows and not errors:
        return {
            "sections_created": 0,
            "items_created": 0,
            "skipped": parsed.skipped,
            "errors": ["Файл пуст или не содержит подходящих строк."],
        }

    agg = EstimateSection.objects.filter(project=project).aggregate(m=Max("order"))
    next_section_order = (agg.get("m") or 0) + 1
    sections_created = 0
    items_created = 0
    err_count = 0

    active_section: EstimateSection | None = None
    section_row_fallback = 0

    with transaction.atomic():
        for row in parsed.rows:
            if row.kind == "section":
                sec_order = _section_order_from_list_no(
                    row.list_no, next_section_order
                )
                active_section = EstimateSection.objects.create(
                    project=project,
                    name=normalize_estimate_name(row.name)[:255],
                    order=sec_order,
                    header_style=(row.header_accent or "")[:16],
                )
                if sec_order >= next_section_order:
                    next_section_order = sec_order + 1
                sections_created += 1
                section_row_fallback = 0
                EstimateItem.objects.create(
                    section=active_section,
                    name=active_section.name[:ESTIMATE_ITEM_NAME_MAX_LENGTH],
                    type=EstimateItem.TYPE_LABOR,
                    unit="—",
                    quantity=Decimal("0"),
                    cost_price=Decimal("0"),
                    markup_percent=Decimal("0"),
                    order=0,
                    is_subsection_header=True,
                )
                continue

            if active_section is None:
                parsed.skipped += 1
                continue

            unit = normalize_excel_unit(row.unit)[:128]
            qty = row.quantity
            name = normalize_estimate_name(row.name)[
                :ESTIMATE_ITEM_NAME_MAX_LENGTH
            ]
            if not name or not unit or qty is None:
                parsed.skipped += 1
                continue

            section_row_fallback += 1
            pos_no = (row.list_no or str(section_row_fallback)).strip()[:16]
            item_order = (
                active_section.items.aggregate(m=Max("order"))["m"] or 0
            ) + 1
            try:
                EstimateItem.objects.create(
                    section=active_section,
                    name=name,
                    type=EstimateItem.TYPE_LABOR,
                    unit=unit[:128],
                    quantity=qty,
                    cost_price=Decimal("0"),
                    markup_percent=Decimal("0"),
                    order=item_order,
                    pdf_pos_no=pos_no,
                )
                items_created += 1
            except Exception as exc:  # noqa: BLE001
                err_count += 1
                errors.append(f"Строка {row.source_row}: {exc}")

    _scrub_project_estimate_names(project)

    return {
        "sections_created": sections_created,
        "items_created": items_created,
        "skipped": parsed.skipped,
        "errors": errors,
        "error_count": err_count,
    }


def _scrub_project_estimate_names(project: Project) -> None:
    """Приводит уже сохранённые названия к виду без английского дубляжа."""
    for sec in EstimateSection.objects.filter(project=project).only(
        "pk", "name"
    ):
        clean = normalize_estimate_name(sec.name)[:255]
        if clean and clean != sec.name:
            EstimateSection.objects.filter(pk=sec.pk).update(name=clean)
    for item in EstimateItem.objects.filter(section__project=project).only(
        "pk", "name", "unit"
    ):
        clean_name = normalize_estimate_name(item.name)
        if clean_name and clean_name != (item.name or ""):
            EstimateItem.objects.filter(pk=item.pk).update(name=clean_name)
        clean_unit = normalize_excel_unit(item.unit or "")
        if clean_unit and clean_unit != (item.unit or ""):
            EstimateItem.objects.filter(pk=item.pk).update(unit=clean_unit[:128])
