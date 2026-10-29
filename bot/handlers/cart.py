from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from apps.catalog.models import Product
from apps.shops.utils import fmt_money
from bot import keyboards, texts
from bot.callbacks import CartCB
from bot.utils import get_cart, set_cart, swap

router = Router(name="cart")


async def render_cart(shop, state: FSMContext):
    """(matn, klaviatura). Mavjud bo'lmay qolgan mahsulotlar savatdan olib tashlanadi."""
    cart = await get_cart(state)
    products = {p.pk: p async for p in Product.objects.filter(shop=shop, pk__in=cart.keys(), is_available=True)}
    cart = {pid: qty for pid, qty in cart.items() if pid in products}
    await set_cart(state, cart)
    if not cart:
        return texts.CART_EMPTY, None
    items = [(products[pid], qty) for pid, qty in cart.items()]
    total = sum(p.price * q for p, q in items)
    lines = ["🧺 <b>Savatingiz</b>", ""]
    lines += [f"{i}. {p.name} ×{q} — {fmt_money(p.price * q, shop.currency)}" for i, (p, q) in enumerate(items, 1)]
    lines += ["", f"<b>Jami: {fmt_money(total, shop.currency)}</b>"]
    return "\n".join(lines), keyboards.cart_kb(items)


@router.message(F.text == texts.BTN_CART)
async def open_cart(message: Message, state: FSMContext, shop):
    await state.set_state(None)
    text, kb = await render_cart(shop, state)
    await message.answer(text, reply_markup=kb)


@router.callback_query(CartCB.filter(F.act.in_({"show", "inc", "dec", "clear"})))
async def cart_action(cb: CallbackQuery, callback_data: CartCB, state: FSMContext, bot: Bot, shop):
    cart = await get_cart(state)
    pid = callback_data.id
    if callback_data.act == "inc" and pid in cart:
        cart[pid] = min(cart[pid] + 1, 50)
    elif callback_data.act == "dec" and pid in cart:
        cart[pid] -= 1
        if cart[pid] <= 0:
            del cart[pid]
    elif callback_data.act == "clear":
        cart = {}
    await set_cart(state, cart)
    text, kb = await render_cart(shop, state)
    await swap(cb, bot, text, kb)
    await cb.answer()
