import logging

from django.utils import timezone

from apps.orders.models import Order

logger = logging.getLogger(__name__)


def mark_paid(payment) -> None:
    """To'lov muvaffaqiyatli bo'lganda chaqiriladi (transaction ichida)."""
    order = Order.objects.select_for_update().get(pk=payment.order_id)
    order.payment_status = Order.PaymentStatus.PAID
    order.save(update_fields=["payment_status", "updated_at"])


def mark_refunded(payment) -> None:
    order = Order.objects.select_for_update().get(pk=payment.order_id)
    order.payment_status = Order.PaymentStatus.UNPAID
    order.save(update_fields=["payment_status", "updated_at"])


def notify_paid(order_id: int) -> None:
    """Bot orqali do'konga va mijozga xabar. Xabar yuborilmasa ham to'lov buzilmaydi."""
    from bot import flows, notify

    order = Order.objects.select_related("shop").get(pk=order_id)
    notify.run_with_bot(order.shop, lambda bot: flows.on_paid(bot, order_id))


def now_ms() -> int:
    return int(timezone.now().timestamp() * 1000)
