"""Генерация QR для карточки инвентаря."""
from __future__ import annotations

import io
from typing import TYPE_CHECKING

import qrcode
from django.core.files.base import ContentFile
from django.urls import reverse

if TYPE_CHECKING:
    from django.http import HttpRequest

    from .models import WarehouseInventoryItem


def item_qr_target_url(request: HttpRequest, item_id: int) -> str:
    rel = reverse("warehouse_inventory_erp") + f"?item={item_id}"
    return request.build_absolute_uri(rel)


def qr_png_bytes(url: str, box_size: int = 6) -> bytes:
    qr = qrcode.QRCode(version=1, box_size=box_size, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def ensure_qr_image_file(item: WarehouseInventoryItem, request: HttpRequest) -> None:
    if item.qr_image:
        return
    url = item_qr_target_url(request, item.pk)
    data = qr_png_bytes(url)
    item.qr_image.save(f"inv_{item.pk}.png", ContentFile(data), save=False)
    item.save(update_fields=["qr_image", "updated_at"])
