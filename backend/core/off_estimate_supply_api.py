"""API заявок вне сметы — редактирование после создания запрещено (workflow)."""
from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_POST

from .rbac import permission_required


@login_required
@require_POST
@permission_required("view_off_estimate_supply")
def api_off_estimate_request_update(
    request: HttpRequest, pk: int, req_id: int
) -> JsonResponse:
    return JsonResponse(
        {
            "ok": False,
            "error": "readonly",
            "message": "Редактирование заявки после создания запрещено.",
        },
        status=403,
    )


@login_required
@require_POST
@permission_required("view_off_estimate_supply")
def api_off_estimate_item_update(
    request: HttpRequest, pk: int, req_id: int, item_id: int
) -> JsonResponse:
    return JsonResponse(
        {
            "ok": False,
            "error": "readonly",
            "message": "Редактирование позиций после создания заявки запрещено.",
        },
        status=403,
    )


@login_required
@require_POST
@permission_required("edit_off_estimate_supply")
def api_off_estimate_receive_warehouse(
    request: HttpRequest, pk: int, req_id: int, item_id: int
) -> JsonResponse:
    return JsonResponse(
        {
            "ok": False,
            "error": "use_orders",
            "message": "Приём на склад выполняется из раздела «Заказы».",
        },
        status=400,
    )
