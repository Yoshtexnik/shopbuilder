import re

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove
from asgiref.sync import sync_to_async

from apps.cafe import services as cafe
from apps.orders.models import Order
from apps.orders.services import OrderError, build_quote, create_order, payment_methods
from apps.shops.utils import fmt_money
from bot import flows, keyboards, texts
from bot.callbacks import CartCB, CheckoutCB
from bot.states import Checkout
from bot.utils import get_cart, set_cart

router = Router(name="checkout")

DELIVERY_LABELS = {"delivery": "🚚 Yetkazib berish", "pickup": "🏃 Olib ketaman"}
PHONE_RE = re.compile(r"^\+?\d{9,13}$")


def normalize_phone(raw: str) -> str | None:
    digits = re.sub(r"[\s\-()]", "", raw)
    if not PHONE_RE.match(digits):
        return None
    if len(digits) == 9:  # 901234567
        digits = "998" + digits
    return "+" + digits.lstrip("+")


async def cancel_checkout(bot: Bot, chat_id: int, state: FSMContext, shop) -> None:
    await state.set_state(None)
    await bot.send_message(chat_id, texts.CHECKOUT_CANCELLED, reply_markup=keyboards.main_menu(shop))


# --- 1. boshlash ------------------------------------------------------------

@router.callback_query(CartCB.filter(F.act == "checkout"))
async def begin(cb: CallbackQuery, state: FSMContext, bot: Bot, shop, customer):
    cart = await get_cart(state)
    try:
        await sync_to_async(build_quote)(shop, cart, need_fee=False)  # ish vaqti, mavjudlik, minimal summa
    except OrderError as exc:
        await cb.answer(str(exc), show_alert=True)
        return
    types = await sync_to_async(cafe.available_delivery_types)(shop)
    if not types:
        await cb.answer(texts.SHOP_CLOSED, show_alert=True)
        return
    await cb.answer()
    if len(types) == 1:
        await state.update_data(delivery_type=str(types[0]))
        await after_type(bot, cb.from_user.id, state, shop, customer)
        return
    await state.set_state(Checkout.delivery_type)
    await bot.send_message(cb.from_user.id, "Buyurtma turini tanlang:",
                           reply_markup=keyboards.choose_kb([(t, DELIVERY_LABELS[t]) for t in types], "type"))


@router.callback_query(CheckoutCB.filter(F.act == "cancel"))
async def cancel_cb(cb: CallbackQuery, state: FSMContext, bot: Bot, shop):
    await cb.answer()
    await cancel_checkout(bot, cb.from_user.id, state, shop)


@router.message(F.text == texts.BTN_CANCEL)
async def cancel_msg(message: Message, state: FSMContext, bot: Bot, shop):
    await cancel_checkout(bot, message.chat.id, state, shop)


# --- 2. buyurtma turi -------------------------------------------------------

@router.callback_query(Checkout.delivery_type, CheckoutCB.filter(F.act == "type"))
async def choose_type(cb: CallbackQuery, callback_data: CheckoutCB, state: FSMContext, bot: Bot, shop, customer):
    await cb.answer()
    types = [str(t) for t in await sync_to_async(cafe.available_delivery_types)(shop)]
    if callback_data.val not in types:
        return
    await state.update_data(delivery_type=callback_data.val)
    await after_type(bot, cb.from_user.id, state, shop, customer)


async def after_type(bot: Bot, chat_id: int, state: FSMContext, shop, customer) -> None:
    data = await state.get_data()
    if data["delivery_type"] == "delivery":
        await state.set_state(Checkout.location)
        needs = await sync_to_async(cafe.requires_location)(shop) if shop.template == shop.Template.CAFE else False
        await bot.send_message(
            chat_id,
            "📍 Yetkazish manzilini lokatsiya sifatida yuboring." if needs else "📍 Lokatsiyangizni yuboring yoki manzilni yozing.",
            reply_markup=keyboards.location_kb(allow_address_only=not needs),
        )
    else:
        await state.update_data(lat=None, lng=None, address="")
        await ask_phone(bot, chat_id, state, shop, customer)


# --- 3. lokatsiya va manzil -------------------------------------------------

@router.message(Checkout.location, F.location)
async def got_location(message: Message, state: FSMContext, bot: Bot, shop):
    cart = await get_cart(state)
    lat, lng = message.location.latitude, message.location.longitude
    try:
        quote = await sync_to_async(build_quote)(shop, cart, "delivery", lat, lng)
    except OrderError as exc:
        await message.answer(f"⚠️ {exc}")
        return
    await state.update_data(lat=lat, lng=lng)
    await state.set_state(Checkout.address)
    await message.answer(
        f"🚚 Yetkazish narxi: {fmt_money(quote.delivery_fee, shop.currency)}\n\nManzilni yozing (ko'cha, uy, mo'ljal):",
        reply_markup=keyboards.cancel_only(),
    )


@router.message(Checkout.location, F.text == texts.BTN_ADDRESS_ONLY)
async def address_only(message: Message, state: FSMContext, shop):
    await state.update_data(lat=None, lng=None)
    await state.set_state(Checkout.address)
    await message.answer("Manzilni yozing (ko'cha, uy, mo'ljal):", reply_markup=keyboards.cancel_only())


@router.message(Checkout.location)
async def location_expected(message: Message):
    await message.answer("Pastdagi «📍 Lokatsiyani yuborish» tugmasini bosing.")


@router.message(Checkout.address, F.text)
async def got_address(message: Message, state: FSMContext, bot: Bot, shop, customer):
    address = message.text.strip()
    if len(address) < 5:
        await message.answer("Manzil juda qisqa. Ko'cha va uy raqamini yozing.")
        return
    await state.update_data(address=address[:300])
    await ask_phone(bot, message.chat.id, state, shop, customer)


# --- 4. telefon -------------------------------------------------------------

async def ask_phone(bot: Bot, chat_id: int, state: FSMContext, shop, customer) -> None:
    if customer is not None and customer.phone:
        await state.update_data(phone=customer.phone)
        await ask_payment(bot, chat_id, state, shop)
        return
    await state.set_state(Checkout.phone)
    await bot.send_message(chat_id, "📱 Telefon raqamingizni yuboring (+998901234567):", reply_markup=keyboards.phone_kb())


@router.message(Checkout.phone, F.contact)
async def got_contact(message: Message, state: FSMContext, bot: Bot, shop):
    if message.contact.user_id != message.from_user.id:
        await message.answer("Iltimos, o'zingizning raqamingizni yuboring.")
        return
    phone = normalize_phone(message.contact.phone_number)
    await state.update_data(phone=phone)
    await message.answer("✅ Raqam saqlandi", reply_markup=ReplyKeyboardRemove())
    await ask_payment(bot, message.chat.id, state, shop)


@router.message(Checkout.phone, F.text)
async def got_phone_text(message: Message, state: FSMContext, bot: Bot, shop):
    phone = normalize_phone(message.text)
    if phone is None:
        await message.answer("Raqam noto'g'ri. Namuna: +998901234567")
        return
    await state.update_data(phone=phone)
    await message.answer("✅ Raqam saqlandi", reply_markup=ReplyKeyboardRemove())
    await ask_payment(bot, message.chat.id, state, shop)


# --- 5. to'lov usuli --------------------------------------------------------

async def ask_payment(bot: Bot, chat_id: int, state: FSMContext, shop) -> None:
    methods = payment_methods(shop)
    if not methods:
        await state.set_state(None)
        await bot.send_message(chat_id, "Hozircha to'lov usullari sozlanmagan. Do'kon bilan bog'laning.",
                               reply_markup=keyboards.main_menu(shop))
        return
    if len(methods) == 1:
        await state.update_data(payment_method=str(methods[0][0]))
        await ask_confirm(bot, chat_id, state, shop)
        return
    await state.set_state(Checkout.payment)
    await bot.send_message(chat_id, "To'lov usulini tanlang:", reply_markup=keyboards.choose_kb(list(methods), "pay"))


@router.callback_query(Checkout.payment, CheckoutCB.filter(F.act == "pay"))
async def choose_payment(cb: CallbackQuery, callback_data: CheckoutCB, state: FSMContext, bot: Bot, shop):
    await cb.answer()
    if callback_data.val not in {str(c) for c, _ in payment_methods(shop)}:
        return
    await state.update_data(payment_method=callback_data.val)
    await ask_confirm(bot, cb.from_user.id, state, shop)


# --- 6. tasdiqlash ----------------------------------------------------------

async def ask_confirm(bot: Bot, chat_id: int, state: FSMContext, shop) -> None:
    data = await state.get_data()
    cart = await get_cart(state)
    try:
        quote = await sync_to_async(build_quote)(shop, cart, data["delivery_type"], data.get("lat"), data.get("lng"))
    except OrderError as exc:
        await state.set_state(None)
        await bot.send_message(chat_id, f"⚠️ {exc}", reply_markup=keyboards.main_menu(shop))
        return
    lines = ["🧾 <b>Buyurtmangizni tekshiring</b>", ""]
    lines += [f"• {l.product.name} ×{l.qty} — {fmt_money(l.total, shop.currency)}" for l in quote.lines]
    lines.append("")
    if data["delivery_type"] == "delivery":
        lines.append(f"Yetkazish: {fmt_money(quote.delivery_fee, shop.currency)}")
        lines.append(f"📍 {data.get('address') or 'lokatsiya bo`yicha'}")
    else:
        lines.append("🏃 Olib ketish")
    lines.append(f"<b>Jami: {fmt_money(quote.total, shop.currency)}</b>")
    lines.append(f"📞 {data.get('phone', '—')}")
    lines.append(f"To'lov: {Order.PaymentMethod(data['payment_method']).label}")
    await state.set_state(Checkout.confirm)
    await bot.send_message(chat_id, "\n".join(lines), reply_markup=ReplyKeyboardRemove())
    await bot.send_message(chat_id, "Hammasi to'g'rimi?", reply_markup=keyboards.confirm_kb())


@router.callback_query(Checkout.confirm, CheckoutCB.filter(F.act == "confirm"))
async def confirm(cb: CallbackQuery, state: FSMContext, bot: Bot, shop, customer):
    data = await state.get_data()
    cart = await get_cart(state)
    await state.set_state(None)  # qo'sh bosishdan himoya: ikkinchi callback holat filtridan o'tmaydi
    try:
        order = await sync_to_async(create_order)(
            shop=shop, customer=customer, cart=cart, delivery_type=data["delivery_type"],
            payment_method=data["payment_method"], phone=data.get("phone", ""), address=data.get("address", ""),
            lat=data.get("lat"), lng=data.get("lng"),
        )
    except OrderError as exc:
        await state.set_state(Checkout.confirm)
        await cb.answer(str(exc), show_alert=True)
        return
    await set_cart(state, {})
    await cb.answer("✅ Buyurtma yuborildi")
    try:
        await cb.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await bot.send_message(cb.from_user.id, "Buyurtma qabul qilindi 👇", reply_markup=keyboards.main_menu(shop))
    await flows.publish_order(bot, order.pk)
