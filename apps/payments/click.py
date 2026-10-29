import hashlib
import logging
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.orders.models import Order
from apps.shops.models import Shop

from . import services
from .models import Payment

logger = logging.getLogger(__name__)

OK, SIGN_FAILED, BAD_AMOUNT, BAD_ACTION, ALREADY_PAID, NO_ORDER, NO_TX, UPDATE_FAILED, BAD_REQUEST, CANCELLED = 0, -1, -2, -3, -4, -5, -6, -7, -8, -9
NOTES = {
    OK: "Success", SIGN_FAILED: "SIGN CHECK FAILED!", BAD_AMOUNT: "Incorrect parameter amount",
    BAD_ACTION: "Action not found", ALREADY_PAID: "Already paid", NO_ORDER: "Order not found",
    NO_TX: "Transaction not found", UPDATE_FAILED: "Failed to update order", BAD_REQUEST: "Error in request from click",
    CANCELLED: "Transaction cancelled",
}
PREPARE_FIELDS = ("click_trans_id", "service_id", "merchant_trans_id", "amount", "action", "sign_time", "sign_string")


def _md5(*parts) -> str:
    return hashlib.md5("".join(str(p) for p in parts).encode()).hexdigest()


def _reply(params, code: int, **extra):
    body = {
        "click_trans_id": params.get("click_trans_id"),
        "merchant_trans_id": params.get("merchant_trans_id"),
        "error": code,
        "error_note": NOTES[code],
    }
    body.update(extra)
    return JsonResponse(body)


@csrf_exempt
@require_POST
def click_view(request, shop_id: int):
    shop = Shop.objects.filter(pk=shop_id, is_active=True).first()
    params = request.POST
    if shop is None or not shop.click_enabled:
        return _reply(params, BAD_REQUEST)
    if any(f not in params for f in PREPARE_FIELDS):
        return _reply(params, BAD_REQUEST)
    if params["service_id"] != shop.click_service_id:
        return _reply(params, BAD_REQUEST)

    try:
        action = int(params["action"])
        amount = Decimal(params["amount"])
    except (ValueError, InvalidOperation):
        return _reply(params, BAD_REQUEST)

    if action == 0:
        expected = _md5(params["click_trans_id"], params["service_id"], shop.click_secret_key,
                        params["merchant_trans_id"], params["amount"], params["action"], params["sign_time"])
    elif action == 1:
        if "merchant_prepare_id" not in params:
            return _reply(params, BAD_REQUEST)
        expected = _md5(params["click_trans_id"], params["service_id"], shop.click_secret_key,
                        params["merchant_trans_id"], params["merchant_prepare_id"], params["amount"],
                        params["action"], params["sign_time"])
    else:
        return _reply(params, BAD_ACTION)
    if expected != params["sign_string"]:
        return _reply(params, SIGN_FAILED)

    paid_order_id = None
    with transaction.atomic():
        try:
            order = Order.objects.select_for_update().get(pk=int(params["merchant_trans_id"]), shop=shop)
        except (Order.DoesNotExist, ValueError):
            return _reply(params, NO_ORDER)

        if action == 0:
            response = _prepare(request, params, order, amount)
        else:
            response, paid_order_id = _complete(params, order, amount)
    if paid_order_id:
        services.notify_paid(paid_order_id)
    return response


def _prepare(request, params, order: Order, amount: Decimal):
    if order.payment_status == Order.PaymentStatus.PAID:
        return _reply(params, ALREADY_PAID)
    if order.status == Order.Status.CANCELLED:
        return _reply(params, CANCELLED)
    if amount != order.total:
        return _reply(params, BAD_AMOUNT)
    payment, _ = Payment.objects.get_or_create(
        provider=Payment.Provider.CLICK, external_id=params["click_trans_id"],
        defaults={"order": order, "amount": order.total, "create_time_ms": services.now_ms()},
    )
    if payment.state == Payment.CANCELLED:
        return _reply(params, CANCELLED)
    return _reply(params, OK, merchant_prepare_id=payment.pk)


def _complete(params, order: Order, amount: Decimal):
    try:
        payment = Payment.objects.select_for_update().get(
            pk=int(params["merchant_prepare_id"]), provider=Payment.Provider.CLICK, order=order,
        )
    except (Payment.DoesNotExist, ValueError):
        return _reply(params, NO_TX), None
    if payment.state == Payment.PERFORMED:
        return _reply(params, ALREADY_PAID), None
    if payment.state == Payment.CANCELLED:
        return _reply(params, CANCELLED), None
    if amount != payment.amount:
        return _reply(params, BAD_AMOUNT), None
    if int(params.get("error", 0)) < 0:
        payment.state = Payment.CANCELLED
        payment.cancel_time_ms = services.now_ms()
        payment.save(update_fields=["state", "cancel_time_ms"])
        return _reply(params, CANCELLED), None
    payment.state = Payment.PERFORMED
    payment.perform_time_ms = services.now_ms()
    payment.save(update_fields=["state", "perform_time_ms"])
    services.mark_paid(payment)
    return _reply(params, OK, merchant_confirm_id=payment.pk), order.pk
