from aiogram import Bot, Router
from aiogram.types import CallbackQuery
from asgiref.sync import sync_to_async

from apps.orders.models import Order
from apps.orders.services import OrderError, change_status
from bot import flows
from bot.callbacks import StatusCB

router = Router(name="staff")


@router.callback_query(StatusCB.filter())
async def on_status(cb: CallbackQuery, callback_data: StatusCB, bot: Bot, shop):
    # Faqat do'konning buyurtmalar guruhidan kelgan bosishlar qabul qilinadi.
    if not cb.message or not shop.order_chat_id or cb.message.chat.id != shop.order_chat_id:
        await cb.answer("Ruxsat yo'q", show_alert=True)
        return
    if callback_data.st not in Order.Status.values:
        await cb.answer()
        return
    try:
        order, changed = await sync_to_async(change_status)(callback_data.id, callback_data.st, shop=shop)
    except (OrderError, Order.DoesNotExist):
        await cb.answer("Buyurtma topilmadi", show_alert=True)
        return
    if not changed:
        await cb.answer("Holat allaqachon o'zgargan")
        return
    await cb.answer("✅")
    await flows.push_status(bot, order.pk)
