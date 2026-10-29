"""Bot va admin/to'lov oqimlari uchun umumiy xabar yuborish mantiqi."""
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from asgiref.sync import sync_to_async

from apps.orders.models import Order
from apps.orders.services import render_order
from apps.payments.links import pay_url

from . import keyboards, texts

logger = logging.getLogger(__name__)


def _load(order_id: int):
    order = Order.objects.select_related("shop", "customer", "courier").get(pk=order_id)
    return order, render_order(order, staff=True), render_order(order, staff=False), pay_url(order)


async def _send_safely(coro) -> bool:
    try:
        await coro
        return True
    except TelegramAPIError as exc:
        logger.warning("Telegram xabari yuborilmadi: %s", exc)
        return False


async def publish_order(bot: Bot, order_id: int) -> None:
    """Yangi buyurtma: do'kon guruhiga kartochka, mijozga tasdiq (+ to'lov tugmasi)."""
    order, staff_text, _, url = await sync_to_async(_load)(order_id)
    shop = order.shop
    if shop.order_chat_id:
        try:
            msg = await bot.send_message(shop.order_chat_id, staff_text, reply_markup=keyboards.staff_kb(order),
                                         disable_web_page_preview=True)
            order.staff_message_id = msg.message_id
            await order.asave(update_fields=["staff_message_id"])
        except TelegramAPIError as exc:
            logger.warning("Buyurtma guruhiga yuborilmadi (shop=%s): %s", shop.pk, exc)
    else:
        logger.warning("Shop %s uchun order_chat_id o'rnatilmagan, buyurtma #%s guruhga yuborilmadi", shop.pk, order.number)
    markup = None
    if url:
        label = "💳 Click orqali to'lash" if order.payment_method == "click" else "💳 Payme orqali to'lash"
        markup = keyboards.pay_kb(url, label)
    await _send_safely(bot.send_message(order.customer.tg_id, texts.order_accepted(order), reply_markup=markup))


async def refresh_staff_message(bot: Bot, order: Order, staff_text: str) -> None:
    if not (order.staff_message_id and order.shop.order_chat_id):
        return
    try:
        await bot.edit_message_text(staff_text, chat_id=order.shop.order_chat_id, message_id=order.staff_message_id,
                                    reply_markup=keyboards.staff_kb(order), disable_web_page_preview=True)
    except TelegramBadRequest as exc:
        if "not modified" not in str(exc):
            logger.warning("Guruh xabarini yangilab bo'lmadi: %s", exc)
    except TelegramAPIError as exc:
        logger.warning("Guruh xabarini yangilab bo'lmadi: %s", exc)


async def push_status(bot: Bot, order_id: int) -> None:
    """Holat o'zgargandan keyin: guruh kartochkasi, mijoz va (yo'lda bo'lsa) kuryer."""
    order, staff_text, _, _ = await sync_to_async(_load)(order_id)
    await refresh_staff_message(bot, order, staff_text)
    message = texts.status_for_customer(order)
    if message:
        await _send_safely(bot.send_message(order.customer.tg_id, f"#{order.number}: {message}"))
    if order.status == "delivering" and order.courier:
        await _send_safely(bot.send_message(order.courier.tg_id, f"🛵 Sizga yangi buyurtma:\n\n{staff_text}",
                                            disable_web_page_preview=True))
        if order.lat is not None and order.lng is not None:
            await _send_safely(bot.send_location(order.courier.tg_id, order.lat, order.lng))


async def on_paid(bot: Bot, order_id: int) -> None:
    order, staff_text, _, _ = await sync_to_async(_load)(order_id)
    await refresh_staff_message(bot, order, staff_text)
    if order.shop.order_chat_id:
        await _send_safely(bot.send_message(order.shop.order_chat_id, f"💳 #{order.number} buyurtma to'landi."))
    await _send_safely(bot.send_message(order.customer.tg_id, f"💳 #{order.number} buyurtma uchun to'lov qabul qilindi. Rahmat!"))
