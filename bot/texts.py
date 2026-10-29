import html

from apps.shops.utils import fmt_money

BTN_MENU = "🍽 Menyu"
BTN_CART = "🧺 Savat"
BTN_ORDERS = "📦 Buyurtmalarim"
BTN_CONTACT = "📞 Aloqa"
BTN_CANCEL = "❌ Bekor qilish"
BTN_SEND_LOCATION = "📍 Lokatsiyani yuborish"
BTN_ADDRESS_ONLY = "📝 Faqat manzilni yozaman"
BTN_SEND_PHONE = "📱 Raqamni yuborish"

SHOP_CLOSED = "Do'kon hozircha buyurtma qabul qilmayapti. Keyinroq urinib ko'ring."
CART_EMPTY = "🧺 Savatingiz bo'sh. Menyudan tanlang."
MENU_EMPTY = "Menyu hali to'ldirilmagan."
CHECKOUT_CANCELLED = "Buyurtma rasmiylashtirish bekor qilindi. Savatingiz saqlandi."

STATUS_FOR_CUSTOMER = {
    "accepted": "✅ Buyurtmangiz qabul qilindi, tayyorlanmoqda.",
    "delivering": "🚚 Buyurtmangiz yo'lda!",
    "cancelled": "❌ Buyurtmangiz bekor qilindi.",
}


def status_for_customer(order) -> str:
    if order.status == "done":
        if order.delivery_type == "pickup":
            return "✔️ Buyurtmangiz tayyor, olib ketishingiz mumkin. Yoqimli ishtaha!"
        return "✔️ Buyurtmangiz yetkazildi. Yoqimli ishtaha!"
    return STATUS_FOR_CUSTOMER.get(order.status, "")


def welcome(shop) -> str:
    return shop.welcome_text or f"Assalomu alaykum! <b>{html.escape(shop.name)}</b> do'koniga xush kelibsiz.\nMenyudan tanlang."


def product_card(product, shop) -> str:
    text = f"<b>{html.escape(product.name)}</b>\n{fmt_money(product.price, shop.currency)}"
    if product.description:
        text += f"\n\n{html.escape(product.description[:600])}"
    return text


def order_accepted(order) -> str:
    text = f"✅ Buyurtma #{order.number} qabul qilindi. Jami: {fmt_money(order.total, order.shop.currency)}."
    if order.payment_method != "cash":
        text += "\nTo'lash uchun quyidagi tugmani bosing."
    else:
        text += "\nTez orada javob beramiz."
    return text
