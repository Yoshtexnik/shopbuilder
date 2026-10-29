from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from asgiref.sync import sync_to_async

from apps.orders.models import Order
from apps.orders.services import OrderError, cancel_by_customer, render_order
from bot import flows, keyboards, texts
from bot.callbacks import MyOrderCB
from bot.utils import swap

router = Router(name="my_orders")


async def _recent(shop, customer):
    return [o async for o in Order.objects.filter(shop=shop, customer=customer).order_by("-id")[:8]]


@router.message(F.text == texts.BTN_ORDERS)
async def my_orders(message: Message, state: FSMContext, shop, customer):
    await state.set_state(None)
    orders = await _recent(shop, customer)
    if not orders:
        await message.answer("Hali buyurtmalaringiz yo'q.")
        return
    await message.answer("Oxirgi buyurtmalaringiz:", reply_markup=keyboards.my_orders_kb(orders, shop))


def _card(order_id: int, customer):
    order = Order.objects.select_related("shop", "customer", "courier").get(pk=order_id, customer=customer)
    return order, render_order(order)


@router.callback_query(MyOrderCB.filter(F.act == "list"))
async def back_to_list(cb: CallbackQuery, bot: Bot, shop, customer):
    orders = await _recent(shop, customer)
    await swap(cb, bot, "Oxirgi buyurtmalaringiz:", keyboards.my_orders_kb(orders, shop))
    await cb.answer()


@router.callback_query(MyOrderCB.filter(F.act == "view"))
async def view(cb: CallbackQuery, callback_data: MyOrderCB, bot: Bot, customer):
    try:
        order, text = await sync_to_async(_card)(callback_data.id, customer)
    except Order.DoesNotExist:
        await cb.answer("Buyurtma topilmadi", show_alert=True)
        return
    await swap(cb, bot, text, keyboards.my_order_kb(order))
    await cb.answer()


@router.callback_query(MyOrderCB.filter(F.act == "cancel"))
async def cancel(cb: CallbackQuery, callback_data: MyOrderCB, bot: Bot, customer):
    try:
        order, changed = await sync_to_async(cancel_by_customer)(callback_data.id, customer)
    except OrderError as exc:
        await cb.answer(str(exc), show_alert=True)
        return
    except Order.DoesNotExist:
        await cb.answer("Buyurtma topilmadi", show_alert=True)
        return
    await cb.answer("Buyurtma bekor qilindi" if changed else "Holat allaqachon o'zgargan")
    order, text = await sync_to_async(_card)(order.pk, customer)
    await swap(cb, bot, text, keyboards.my_order_kb(order))
    if changed:
        await flows.refresh_staff_message(bot, order, await sync_to_async(lambda: render_order(order, staff=True))())
