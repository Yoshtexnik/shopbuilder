from aiogram.types import (InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton,
                           ReplyKeyboardMarkup, WebAppInfo)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from apps.shops.utils import fmt_money

from . import texts
from .callbacks import AddCB, CartCB, CatCB, CheckoutCB, MenuCB, MyOrderCB, ProdCB, QtyCB, StatusCB


def main_menu(shop) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text=texts.BTN_MENU), KeyboardButton(text=texts.BTN_CART)],
        [KeyboardButton(text=texts.BTN_ORDERS), KeyboardButton(text=texts.BTN_CONTACT)],
    ]
    if shop.webapp_enabled and shop.webapp_url.startswith("https://"):
        rows.insert(0, [KeyboardButton(text="🌐 Mini App orqali buyurtma", web_app=WebAppInfo(url=shop.webapp_url))])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def cancel_only() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=texts.BTN_CANCEL)]], resize_keyboard=True)


def location_kb(allow_address_only: bool) -> ReplyKeyboardMarkup:
    rows = [[KeyboardButton(text=texts.BTN_SEND_LOCATION, request_location=True)]]
    if allow_address_only:
        rows.append([KeyboardButton(text=texts.BTN_ADDRESS_ONLY)])
    rows.append([KeyboardButton(text=texts.BTN_CANCEL)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def phone_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=texts.BTN_SEND_PHONE, request_contact=True)], [KeyboardButton(text=texts.BTN_CANCEL)]],
        resize_keyboard=True,
    )


def categories_kb(categories) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for c in categories:
        b.button(text=c.name, callback_data=CatCB(id=c.pk))
    b.adjust(2)
    return b.as_markup()


def products_kb(products, shop) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for p in products:
        b.button(text=f"{p.name} — {fmt_money(p.price, shop.currency)}", callback_data=ProdCB(id=p.pk))
    b.button(text="⬅️ Kategoriyalar", callback_data=MenuCB(act="cats"))
    b.adjust(1)
    return b.as_markup()


def product_kb(product, qty: int, shop) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="➖", callback_data=QtyCB(id=product.pk, q=max(qty - 1, 1)))
    b.button(text=str(qty), callback_data=QtyCB(id=product.pk, q=qty))
    b.button(text="➕", callback_data=QtyCB(id=product.pk, q=min(qty + 1, 20)))
    b.button(text=f"🧺 Savatga · {fmt_money(product.price * qty, shop.currency)}", callback_data=AddCB(id=product.pk, q=qty))
    b.button(text="⬅️ Orqaga", callback_data=MenuCB(act="back"))
    b.adjust(3, 1, 1)
    return b.as_markup()


def after_add_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🧺 Savatni ko'rish", callback_data=CartCB(act="show"))
    b.button(text="🍽 Menyuni davom ettirish", callback_data=MenuCB(act="cats"))
    b.adjust(1)
    return b.as_markup()


def cart_kb(items) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for product, qty in items:
        b.button(text="➖", callback_data=CartCB(act="dec", id=product.pk))
        b.button(text=f"{product.name[:18]} ×{qty}", callback_data=CartCB(act="show"))
        b.button(text="➕", callback_data=CartCB(act="inc", id=product.pk))
    b.button(text="🗑 Tozalash", callback_data=CartCB(act="clear"))
    b.button(text="✅ Buyurtma berish", callback_data=CartCB(act="checkout"))
    b.adjust(*([3] * len(items)), 2)
    return b.as_markup()


def choose_kb(options: list[tuple[str, str]], act: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for value, label in options:
        b.button(text=label, callback_data=CheckoutCB(act=act, val=str(value)))
    b.button(text=texts.BTN_CANCEL, callback_data=CheckoutCB(act="cancel"))
    b.adjust(1)
    return b.as_markup()


def confirm_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="✅ Tasdiqlash", callback_data=CheckoutCB(act="confirm"))
    b.button(text=texts.BTN_CANCEL, callback_data=CheckoutCB(act="cancel"))
    b.adjust(1)
    return b.as_markup()


def pay_kb(url: str, label: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=label, url=url)]])


def staff_kb(order) -> InlineKeyboardMarkup | None:
    s = order.status
    b = InlineKeyboardBuilder()
    if s == "new":
        b.button(text="✅ Qabul qilish", callback_data=StatusCB(id=order.pk, st="accepted"))
    elif s == "accepted":
        if order.delivery_type == "delivery":
            b.button(text="🚚 Yo'lga chiqdi", callback_data=StatusCB(id=order.pk, st="delivering"))
        else:
            b.button(text="✔️ Tayyor", callback_data=StatusCB(id=order.pk, st="done"))
    elif s == "delivering":
        b.button(text="✔️ Yetkazildi", callback_data=StatusCB(id=order.pk, st="done"))
    else:
        return None
    b.button(text="❌ Bekor qilish", callback_data=StatusCB(id=order.pk, st="cancelled"))
    b.adjust(1)
    return b.as_markup()


def my_orders_kb(orders, shop) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for o in orders:
        b.button(text=f"#{o.number} · {o.get_status_display()} · {fmt_money(o.total, shop.currency)}",
                 callback_data=MyOrderCB(id=o.pk, act="view"))
    b.adjust(1)
    return b.as_markup()


def my_order_kb(order) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if order.status == "new" and order.payment_status == "unpaid":
        b.button(text="❌ Buyurtmani bekor qilish", callback_data=MyOrderCB(id=order.pk, act="cancel"))
    b.button(text="⬅️ Buyurtmalarim", callback_data=MyOrderCB(id=0, act="list"))
    b.adjust(1)
    return b.as_markup()
