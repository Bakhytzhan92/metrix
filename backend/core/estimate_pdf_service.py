from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from django.db import transaction
from django.db.models import Max

from .models import (
    ESTIMATE_ITEM_NAME_MAX_LENGTH,
    EstimateItem,
    EstimateSection,
    Project,
)


def _parse_quantity(
    v: Any,
) -> Decimal:
    if v is None or v is False:
        return Decimal("0")
    if isinstance(
        v, (int, float, Decimal)
    ):
        try:
            return Decimal(str(v)
            )
        except (InvalidOperation, ValueError):
            return Decimal("0")
    s = str(v).strip().replace(" ", "")
    s = re.sub(
        r"^[−–—-]+",
        "",
        s,
    )
    s = s.replace(
        ",",
        ".",
    )
    try:
        return Decimal(s)
    except (InvalidOperation, ValueError):
        return Decimal("0")


def apply_local_estimate_rows(
    project: Project, rows: list[dict[str, Any]]
) -> dict[str, int | list[str]]:
    """
    Создаёт разделы и позиции (тип «Работы», нулевые цены).
    Дубликаты в файле и в БД: ключ включает pdf_pos_no + pdf_norm_code, если они есть в строке.
    """
    err: list[str] = []
    file_seen: set[tuple[str, str, str, str, str, str]] = set()
    max_order = (
        EstimateSection.objects.filter(
            project=project
        ).aggregate(
            m=Max("order")
        )["m"]
        or 0
    )
    next_section_order = max_order + 1
    items_created = 0

    with transaction.atomic():
        for r in rows:
            sec_name = (r.get("section") or "Локальная смета").strip()[:255]
            name = (r.get("name") or "").strip()[:ESTIMATE_ITEM_NAME_MAX_LENGTH]
            unit = (r.get("unit") or "шт").strip()[:30]
            qty_d = _parse_quantity(
                r.get("quantity")
            )
            if not name or not unit or qty_d == 0:
                continue
            qk = f"{qty_d:.4f}"
            pos_meta = (r.get("pdf_pos_no") or "").strip()[:16]
            code_meta = (r.get("pdf_norm_code") or "").replace(" ", "")[:64]
            if pos_meta or code_meta:
                fkey = (
                    sec_name,
                    pos_meta,
                    code_meta,
                    name,
                    unit,
                    qk,
                )
            else:
                fkey = (
                    sec_name,
                    "",
                    "",
                    name,
                    unit,
                    qk,
                )
            if fkey in file_seen:
                continue
            file_seen.add(
                fkey
            )
            if pos_meta or code_meta:
                if EstimateItem.objects.filter(
                    section__project=project,
                    section__name=sec_name,
                    name=name,
                    unit=unit,
                    quantity=qty_d,
                    pdf_pos_no=pos_meta,
                    pdf_norm_code=code_meta,
                ).exists():
                    continue
            else:
                if EstimateItem.objects.filter(
                    section__project=project,
                    section__name=sec_name,
                    name=name,
                    unit=unit,
                    quantity=qty_d,
                ).exists():
                    continue
            section = (
                EstimateSection.objects.filter(
                    project=project, name=sec_name
                ).first()
            )
            if not section:
                section = EstimateSection.objects.create(
                    project=project,
                    name=sec_name,
                    order=next_section_order,
                )
                next_section_order += 1
            o = (
                section.items.aggregate(
                    m=Max("order")
                )["m"]
                or 0
            ) + 1
            try:
                EstimateItem.objects.create(
                    section=section,
                    name=name,
                    type=EstimateItem.TYPE_LABOR,
                    unit=unit,
                    quantity=qty_d,
                    cost_price=Decimal("0"),
                    markup_percent=Decimal("0"),
                    order=o,
                    pdf_pos_no=pos_meta,
                    pdf_norm_code=code_meta,
                )
            except Exception as e:  # noqa: BLE001
                err.append(
                    f"{name[:40]}: {e}"
                )
                continue
            items_created += 1

    return {
        "items_created": items_created,
        "errors": err,
    }
