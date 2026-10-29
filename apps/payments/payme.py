import base64
import hmac
import json
import logging

from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from apps.orders.models import Order
from apps.shops.models import Shop

from . import services
from .models import Payment

logger = logging.getLogger(__name__)

TIMEOUT_MS = 12 * 60 * 60 * 1000
REASON_TIMEOUT = 4


class PaymeError(Exception):
    def __init__(self, code: int, uz: str, ru: str = "", en: str = "", data=None):
        self.code, self.data = code, data
        self.message = {"uz": uz, "ru": ru or uz, "en": en or uz}


def _error(rpc_id, err: PaymeError):
    body = {"jsonrpc": "2.0", "id": rpc_id, "error": {"code": err.code, "message": err.message}}
    if err.data is not None:
        body["error"]["data"] = err.data
    return JsonResponse(body)


def _authorized(request, shop: Shop) -> bool:
    header = request.headers.get("Authorization", "")
    if not header.startswith("Basic ") or not shop.payme_key:
        return False
    try:
        login, _, password = base64.b64decode(header[6:]).decode().partition(":")
    except Exception:
        return False
    return login == "Paycom" and hmac.compare_digest(password, shop.payme_key)


@csrf_exempt
def payme_view(request, shop_id: int):
    rpc_id = None
    try:
        if request.method != "POST":
            raise PaymeError(-32300, "POST so'rov kerak", "Требуется POST", "POST required")
        try:
            payload = json.loads(request.body)
            rpc_id = payload.get("id")
            method, params = payload["method"], payload.get("params") or {}
        except (ValueError, KeyError, AttributeError):
            raise PaymeError(-32700, "JSON xato", "Ошибка JSON", "JSON parse error")
        shop = Shop.objects.filter(pk=shop_id, is_active=True).first()
        if shop is None or not _authorized(request, shop):
            raise PaymeError(-32504, "Ruxsat yo'q", "Недостаточно привилегий", "Insufficient privileges")
        handler = HANDLERS.get(method)
        if handler is None:
            raise PaymeError(-32601, "Metod topilmadi", "Метод не найден", "Method not found", data=method)
        result = handler(shop, params)
        return JsonResponse({"jsonrpc": "2.0", "id": rpc_id, "result": result})
    except PaymeError as err:
        return _error(rpc_id, err)
    except Exception:
        logger.exception("Payme: kutilmagan xato")
        return _error(rpc_id, PaymeError(-32400, "Tizim xatosi", "Системная ошибка", "System error"))


# --- yordamchilar -----------------------------------------------------------

def _get_payable_order(shop: Shop, params: dict, *, lock: bool = False) -> Order:
    account = params.get("account") or {}
    try:
        order_id = int(account["order_id"])
    except (KeyError, TypeError, ValueError):
        raise PaymeError(-31050, "Buyurtma topilmadi", "Заказ не найден", "Order not found", data="order_id")
    qs = Order.objects.select_for_update() if lock else Order.objects
    order = qs.filter(pk=order_id, shop=shop).first()
    if order is None:
        raise PaymeError(-31050, "Buyurtma topilmadi", "Заказ не найден", "Order not found", data="order_id")
    if (order.payment_method != Order.PaymentMethod.PAYME or order.status == Order.Status.CANCELLED
            or order.payment_status == Order.PaymentStatus.PAID):
        raise PaymeError(-31051, "Buyurtmani to'lab bo'lmaydi", "Заказ нельзя оплатить", "Order is not payable", data="order_id")
    if int(params.get("amount", -1)) != int(order.total * 100):
        raise PaymeError(-31001, "Summa noto'g'ri", "Неверная сумма", "Wrong amount")
    return order


def _get_payment(shop: Shop, params: dict) -> Payment:
    payment = Payment.objects.select_for_update().filter(
        provider=Payment.Provider.PAYME, external_id=str(params.get("id")), order__shop=shop,
    ).first()
    if payment is None:
        raise PaymeError(-31003, "Tranzaksiya topilmadi", "Транзакция не найдена", "Transaction not found")
    return payment


def _cancel_state(payment: Payment) -> int:
    return Payment.CANCELLED if payment.perform_time_ms == 0 else Payment.CANCELLED_AFTER


def _snapshot(payment: Payment) -> dict:
    return {
        "create_time": payment.create_time_ms,
        "perform_time": payment.perform_time_ms,
        "cancel_time": payment.cancel_time_ms,
        "transaction": str(payment.pk),
        "state": payment.state,
        "reason": payment.reason,
    }


# --- metodlar ---------------------------------------------------------------

def check_perform_transaction(shop, params):
    _get_payable_order(shop, params)
    return {"allow": True}


def _expire(payment: Payment, now: int) -> PaymeError:
    """Muddati o'tgan tranzaksiyani bekor qiladi. Xatoni atomic blokdan TASHQARIDA ko'tarish kerak, aks holda saqlash orqaga qaytadi."""
    payment.state, payment.reason, payment.cancel_time_ms = Payment.CANCELLED, REASON_TIMEOUT, now
    payment.save(update_fields=["state", "reason", "cancel_time_ms"])
    return PaymeError(-31008, "Tranzaksiya muddati tugagan", "Время транзакции истекло", "Transaction timed out")


def create_transaction(shop, params):
    expired = None
    with transaction.atomic():
        payment = Payment.objects.select_for_update().filter(
            provider=Payment.Provider.PAYME, external_id=str(params.get("id")), order__shop=shop,
        ).first()
        now = services.now_ms()
        if payment is not None:
            if payment.state != Payment.CREATED:
                raise PaymeError(-31008, "Amalni bajarib bo'lmaydi", "Невозможно выполнить операцию", "Unable to perform")
            if now - payment.create_time_ms > TIMEOUT_MS:
                expired = _expire(payment, now)
            else:
                return {"create_time": payment.create_time_ms, "transaction": str(payment.pk), "state": payment.state}
        else:
            order = _get_payable_order(shop, params, lock=True)
            if Payment.objects.filter(order=order, provider=Payment.Provider.PAYME, state=Payment.CREATED).exists():
                raise PaymeError(-31099, "Buyurtma uchun boshqa tranzaksiya kutilmoqda", "Для заказа ожидается другая транзакция",
                                 "Another transaction is pending", data="order_id")
            payment = Payment.objects.create(
                order=order, provider=Payment.Provider.PAYME, amount=order.total, external_id=str(params["id"]),
                payme_time=int(params.get("time", now)), create_time_ms=now,
            )
    if expired:
        raise expired
    return {"create_time": payment.create_time_ms, "transaction": str(payment.pk), "state": payment.state}


def perform_transaction(shop, params):
    expired, newly_paid = None, False
    with transaction.atomic():
        payment = _get_payment(shop, params)
        now = services.now_ms()
        if payment.state == Payment.CREATED:
            if now - payment.create_time_ms > TIMEOUT_MS:
                expired = _expire(payment, now)
            else:
                payment.state, payment.perform_time_ms = Payment.PERFORMED, now
                payment.save(update_fields=["state", "perform_time_ms"])
                services.mark_paid(payment)
                newly_paid = True
        elif payment.state != Payment.PERFORMED:
            raise PaymeError(-31008, "Amalni bajarib bo'lmaydi", "Невозможно выполнить операцию", "Unable to perform")
    if expired:
        raise expired
    if newly_paid:
        services.notify_paid(payment.order_id)
    return {"transaction": str(payment.pk), "perform_time": payment.perform_time_ms, "state": payment.state}


@transaction.atomic
def cancel_transaction(shop, params):
    payment = _get_payment(shop, params)
    now = services.now_ms()
    if payment.state == Payment.CREATED:
        payment.state = Payment.CANCELLED
    elif payment.state == Payment.PERFORMED:
        if payment.order.status == Order.Status.DONE:
            raise PaymeError(-31007, "Buyurtma bajarilgan, bekor qilib bo'lmaydi", "Заказ выполнен, отмена невозможна",
                             "Order completed, cannot cancel")
        payment.state = Payment.CANCELLED_AFTER
        services.mark_refunded(payment)
    else:
        return {"transaction": str(payment.pk), "cancel_time": payment.cancel_time_ms, "state": payment.state}
    payment.cancel_time_ms, payment.reason = now, params.get("reason")
    payment.save(update_fields=["state", "cancel_time_ms", "reason"])
    return {"transaction": str(payment.pk), "cancel_time": payment.cancel_time_ms, "state": payment.state}


def check_transaction(shop, params):
    with transaction.atomic():
        payment = _get_payment(shop, params)
    return _snapshot(payment)


def get_statement(shop, params):
    qs = Payment.objects.filter(
        provider=Payment.Provider.PAYME, order__shop=shop,
        payme_time__gte=int(params.get("from", 0)), payme_time__lte=int(params.get("to", 0)),
    ).order_by("payme_time")
    return {"transactions": [
        {"id": p.external_id, "time": p.payme_time, "amount": int(p.amount * 100), "account": {"order_id": str(p.order_id)},
         **_snapshot(p)}
        for p in qs
    ]}


HANDLERS = {
    "CheckPerformTransaction": check_perform_transaction,
    "CreateTransaction": create_transaction,
    "PerformTransaction": perform_transaction,
    "CancelTransaction": cancel_transaction,
    "CheckTransaction": check_transaction,
    "GetStatement": get_statement,
}
