from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from django.db import transaction
from django.db.models import Max

from .models import EstimateItem, EstimateSection, Project


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
    Пропуск дубликатов: в файле (section+name+unit+quantity) и в БД.
    """
    err: list[str] = []
    file_seen: set[tuple[str, str, str, str]] = set()
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
            name = (r.get("name") or "").strip()[:500]
            unit = (r.get("unit") or "шт").strip()[:30]
            qty_d = _parse_quantity(
                r.get("quantity")
            )
            if not name or not unit or qty_d == 0:
                continue
            qk = f"{qty_d:.4f}"
            fkey = (sec_name, name, unit, qk)
            if fkey in file_seen:
                continue
            file_seen.add(
                fkey
            )
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
