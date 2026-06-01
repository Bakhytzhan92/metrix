"""Заявки вне сметы: номера, KPI, экспорт, приём на склад."""

from __future__ import annotations



from datetime import date

from decimal import Decimal, InvalidOperation

from io import BytesIO



from django.db import transaction

from django.db.models import Count, Prefetch, Q

from django.utils import timezone

from openpyxl import Workbook

from openpyxl.styles import Font



from .models import (

    Material,

    OffEstimateSupplyRequest,

    OffEstimateSupplyRequestItem,

    Project,

    Warehouse,

)

from .warehouse_services import apply_incoming





def generate_request_number(company, *, for_date: date | None = None) -> str:

    year = (for_date or date.today()).year

    prefix = f"ZVS-{year}-"

    last = (

        OffEstimateSupplyRequest.objects.filter(

            company=company, number__startswith=prefix

        )

        .order_by("-number")

        .first()

    )

    seq = 1

    if last and last.number:

        try:

            seq = int(last.number.rsplit("-", 1)[-1]) + 1

        except (ValueError, IndexError):

            seq = 1

    return f"{prefix}{seq:04d}"





def normalize_unit(unit: str, custom_unit: str = "") -> str:

    u = (unit or "").strip()

    if u == "__custom__":

        return (custom_unit or "").strip()[:50] or "шт"

    return u[:50] or "шт"





def parse_line_rows_from_post(post) -> tuple[list[dict], list[str]]:

    """Разбор позиций из POST (line_material_name[], …)."""

    names = post.getlist("line_material_name")

    units = post.getlist("line_unit_preset")

    customs = post.getlist("line_unit_custom")

    quantities = post.getlist("line_quantity")

    notes = post.getlist("line_note")

    errors: list[str] = []

    rows: list[dict] = []

    n = max(

        [len(names), len(units), len(quantities), len(notes)],

        default=0,

    )

    for i in range(n):

        name = (names[i] if i < len(names) else "").strip()

        if not name:

            continue

        unit_preset = units[i] if i < len(units) else ""

        unit_custom = customs[i] if i < len(customs) else ""

        unit = normalize_unit(unit_preset, unit_custom)

        if not unit_preset:

            errors.append(f"Позиция {len(rows) + 1}: выберите единицу измерения.")

            continue

        if unit_preset == "__custom__" and not unit_custom.strip():

            errors.append(f"Позиция {len(rows) + 1}: укажите свою единицу.")

            continue

        qty_raw = quantities[i] if i < len(quantities) else ""

        try:

            qty = Decimal(str(qty_raw).replace(",", "."))

        except (InvalidOperation, TypeError):

            errors.append(f"Позиция «{name[:40]}»: некорректное количество.")

            continue

        if qty <= 0:

            errors.append(f"Позиция «{name[:40]}»: количество должно быть > 0.")

            continue

        line_note = (notes[i] if i < len(notes) else "").strip()[:2000]

        rows.append(

            {

                "material_name": name[:255],

                "unit": unit,

                "quantity": qty,

                "note": line_note,

            }

        )

    if not rows and not errors:

        errors.append("Добавьте хотя бы одну позицию с наименованием материала.")

    return rows, errors





@transaction.atomic

def create_off_estimate_request(

    *,

    company,

    project: Project,

    user,

    note: str,

    required_date,

    priority: str,

    lines: list[dict],

) -> OffEstimateSupplyRequest:

    req = OffEstimateSupplyRequest.objects.create(

        company=company,

        project=project,

        number=generate_request_number(company),

        note=note,

        required_date=required_date,

        priority=priority,

        status=OffEstimateSupplyRequest.STATUS_APPROVAL,

        created_by=user,

        assignee=user,

    )

    for idx, line in enumerate(lines):

        OffEstimateSupplyRequestItem.objects.create(

            request=req,

            sort_order=idx,

            material_name=line["material_name"],

            unit=line["unit"],

            quantity=line["quantity"],

            note=line.get("note", ""),

        )

    return req





def delete_off_estimate_request(req: OffEstimateSupplyRequest) -> None:

    """Удалить заявку и все позиции. Запрещено, если материал уже принят на склад."""

    if req.items.filter(warehouse_received=True).exists():

        raise ValueError("warehouse_received")

    req.delete()





def filter_off_estimate_requests(project: Project, params: dict):

    qs = (

        OffEstimateSupplyRequest.objects.filter(project=project)

        .select_related("created_by", "assignee")

        .prefetch_related(

            Prefetch(

                "items",

                queryset=OffEstimateSupplyRequestItem.objects.select_related(

                    "material", "warehouse"

                ).order_by("sort_order", "id"),

            )

        )

        .order_by("-created_at", "-id")

    )

    st = (params.get("status") or "").strip()

    if st in dict(OffEstimateSupplyRequest.STATUS_CHOICES):

        qs = qs.filter(status=st)

    pr = (params.get("priority") or "").strip()

    if pr in dict(OffEstimateSupplyRequest.PRIORITY_CHOICES):

        qs = qs.filter(priority=pr)

    df = (params.get("date_from") or "").strip()

    dt = (params.get("date_to") or "").strip()

    from django.utils.dateparse import parse_date



    d_from = parse_date(df) if df else None

    d_to = parse_date(dt) if dt else None

    if d_from:

        qs = qs.filter(created_at__date__gte=d_from)

    if d_to:

        qs = qs.filter(created_at__date__lte=d_to)

    q = (params.get("q") or "").strip()

    if q:

        qs = qs.filter(

            Q(number__icontains=q)

            | Q(note__icontains=q)

            | Q(items__material_name__icontains=q)

            | Q(items__note__icontains=q)

        ).distinct()

    return qs





def compute_off_estimate_kpis(project: Project) -> dict:

    qs = OffEstimateSupplyRequest.objects.filter(project=project)

    agg = qs.aggregate(

        total=Count("id"),

        pending=Count("id", filter=Q(status=OffEstimateSupplyRequest.STATUS_APPROVAL)),

        purchased=Count(

            "id",

            filter=Q(status=OffEstimateSupplyRequest.STATUS_PURCHASED),

        ),

    )

    return {

        "total": agg["total"] or 0,

        "pending": agg["pending"] or 0,

        "purchased": agg["purchased"] or 0,

    }





def get_or_create_project_warehouse(project: Project) -> Warehouse | None:

    wh = (

        Warehouse.objects.filter(

            company=project.company, project=project, is_deleted=False

        )

        .order_by("id")

        .first()

    )

    if wh:

        return wh

    return (

        Warehouse.objects.filter(

            company=project.company, project__isnull=True, is_deleted=False

        )

        .order_by("id")

        .first()

    )





@transaction.atomic

def receive_item_to_warehouse(

    item: OffEstimateSupplyRequestItem, *, user

) -> Material:

    req = item.request

    if item.warehouse_received:

        raise ValueError("already_received")

    if req.status not in (

        OffEstimateSupplyRequest.STATUS_PARTIAL,

        OffEstimateSupplyRequest.STATUS_PURCHASED,

    ):

        raise ValueError("status_not_ready")

    qty = item.quantity_purchased or item.quantity

    if not qty or qty <= 0:

        raise ValueError("bad_quantity")

    warehouse = get_or_create_project_warehouse(req.project)

    if not warehouse:

        raise ValueError("no_warehouse")

    material = Material.objects.filter(

        company=req.company, name=item.material_name

    ).first()

    if not material:

        material = Material.objects.create(

            company=req.company,

            name=item.material_name,

            unit=item.unit,

            category=Material.CATEGORY_MATERIAL,

            supplier="",

            description=f"Заявка вне сметы {req.number}",

        )

    apply_incoming(

        material=material,

        warehouse=warehouse,

        quantity=qty,

        price=Decimal("0"),

        date=date.today(),

        comment=f"Заявка вне сметы {req.number}",

        supplier="",

        user=user,

    )

    item.material = material

    item.warehouse = warehouse

    item.warehouse_received = True

    item.warehouse_received_at = timezone.now()

    item.save(

        update_fields=[

            "material",

            "warehouse",

            "warehouse_received",

            "warehouse_received_at",

        ]

    )

    return material





def export_off_estimate_xlsx(project: Project, requests) -> BytesIO:

    wb = Workbook()

    ws = wb.active

    ws.title = "Заявки вне сметы"

    headers = [

        "№",

        "Дата",

        "Наименование",

        "Ед. изм.",

        "Количество",

        "Примечание позиции",

        "Фактически закуплено",

        "Статус",

        "Ответственный",

        "Комментарий к заявке",

    ]

    ws.append(headers)

    for cell in ws[1]:

        cell.font = Font(bold=True)

    for req in requests:

        items = list(req.items.all())

        if not items:

            items = [None]

        for line in items:

            ws.append(

                [

                    req.number,

                    req.created_at.strftime("%d.%m.%Y") if req.created_at else "",

                    line.material_name if line else "—",

                    line.unit if line else "",

                    float(line.quantity or 0) if line else 0,

                    (line.note if line else "") or "",

                    float(line.quantity_purchased or 0) if line else 0,

                    req.get_status_display(),

                    (req.assignee.get_username() if req.assignee else ""),

                    req.note or "",

                ]

            )

    buf = BytesIO()

    wb.save(buf)

    buf.seek(0)

    return buf





def export_off_estimate_pdf(project: Project, requests) -> BytesIO:

    import fitz



    doc = fitz.open()

    page = doc.new_page(width=595, height=842)

    y = 40

    page.insert_text(

        (40, y),

        f"Заявки вне сметы — {project.name}",

        fontsize=14,

        fontname="helv",

    )

    y += 24

    page.insert_text((40, y), f"Дата выгрузки: {date.today():%d.%m.%Y}", fontsize=9)

    y += 20

    for req in requests:

        for line in req.items.all():

            if y > 780:

                page = doc.new_page(width=595, height=842)

                y = 40

            note_hint = f" | {line.note[:30]}" if line.note else ""

            text = (

                f"{req.number} | {req.created_at:%d.%m.%Y} | "

                f"{line.material_name[:40]} | {line.quantity} {line.unit}{note_hint} | "

                f"{req.get_status_display()}"

            )

            page.insert_text((40, y), text, fontsize=8, fontname="helv")

            y += 14

    buf = BytesIO(doc.tobytes())

    doc.close()

    buf.seek(0)

    return buf


