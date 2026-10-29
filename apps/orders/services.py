import html
from dataclasses import dataclass
from decimal import Decimal

from django.db import transaction

from apps.cafe import services as cafe
from apps.catalog.models import Product
from apps.shops.models import Shop
from apps.shops.utils import OrderError, fmt_money

from .models import Customer, Order, OrderItem

MAX_QTY = 50

TRANSITIONS = {
    Order.Status.NEW: {Order.Status.ACCEPTED, Order.Status.CANCELLED},
    Order.Status.ACCEPTED: {Order.Status.DELIVERING, Order.Status.DONE, Order.Status.CANCELLED},
    Order.Status.DELIVERING: {Order.Status.DONE, Order.Status.CANCELLED},
    Order.Status.DONE: set(),
    Order.Status.CANCELLED: set(),
}


@dataclass
class QuoteLine:
    product: Product
    qty: int
    price: Decimal

    @property
    def total(self) -> Decimal:
        return self.price * self.qty


@dataclass
class Quote:
    lines: list[QuoteLine]
    subtotal: Decimal
    delivery_fee: Decimal

    @property
    def total(self) -> Decimal:
        return self.subtotal + self.delivery_fee


def payment_methods(shop) -> list[tuple[str, str]]:
    methods = []
    if shop.cash_enabled:
        methods.append((Order.PaymentMethod.CASH, "💵 Naqd"))
    if shop.click_enabled:
        methods.append((Order.PaymentMethod.CLICK, "💳 Click"))
    if shop.payme_enabled:
        methods.append((Order.PaymentMethod.PAYME, "💳 Payme"))
    return methods


def build_quote(shop, cart: dict, delivery_type: str = "pickup", lat=None, lng=None, *, need_fee: bool = True) -> Quote:
    """Savatni serverda qayta hisoblaydi. Narxlar doim bazadan olinadi, mijozdan emas."""
    try:
        cart = {int(k): int(v) for k, v in cart.items()}
    except (TypeError, ValueError):
        raise OrderError("Savat noto'g'ri.")
    if not cart:
        raise OrderError("Savat bo'sh.")
    products = {p.pk: p for p in Product.objects.filter(shop=shop, pk__in=cart.keys())}
    lines = []
    for pid, qty in cart.items():
        product = products.get(pid)
        if product is None or not product.is_available:
            raise OrderError(f"«{product.name if product else 'Mahsulot'}» hozir mavjud emas.")
        if not 1 <= qty <= MAX_QTY:
            raise OrderError(f"«{product.name}» soni 1 dan {MAX_QTY} gacha bo'lishi kerak.")
        lines.append(QuoteLine(product, qty, product.price))
    subtotal = sum((line.total for line in lines), Decimal("0"))
    fee = Decimal("0")
    if shop.template == Shop.Template.CAFE:
        cs = cafe.get_settings(shop)
        cafe.ensure_open(cs)
        if subtotal < cs.min_order_sum:
            raise OrderError(f"Minimal buyurtma summasi: {fmt_money(cs.min_order_sum, shop.currency)}.")
        if need_fee:
            fee = cafe.delivery_fee(cs, delivery_type, lat, lng, subtotal)
    return Quote(lines, subtotal, fee)


@transaction.atomic
def create_order(*, shop, customer: Customer, cart: dict, delivery_type: str, payment_method: str,
                 phone: str = "", address: str = "", lat=None, lng=None, comment: str = "") -> Order:
    shop = Shop.objects.select_for_update().get(pk=shop.pk)
    if not shop.is_active or not shop.is_paid:
        raise OrderError("Do'kon hozir buyurtma qabul qilmayapti.")
    if payment_method not in {code for code, _ in payment_methods(shop)}:
        raise OrderError("Bu to'lov usuli mavjud emas.")
    if delivery_type not in cafe.available_delivery_types(shop):
        raise OrderError("Bu buyurtma turi mavjud emas.")
    if delivery_type == Order.DeliveryType.DELIVERY and not (address.strip() or lat is not None):
        raise OrderError("Yetkazish manzilini kiriting.")
    quote = build_quote(shop, cart, delivery_type, lat, lng)
    shop.order_counter += 1
    shop.save(update_fields=["order_counter"])
    order = Order.objects.create(
        shop=shop, customer=customer, number=shop.order_counter,
        delivery_type=delivery_type, payment_method=payment_method,
        subtotal=quote.subtotal, delivery_fee=quote.delivery_fee, total=quote.total,
        phone=phone or customer.phone, address=address.strip()[:500], lat=lat, lng=lng, comment=comment.strip()[:500],
    )
    OrderItem.objects.bulk_create([
        OrderItem(order=order, product=line.product, name_snapshot=line.product.name, qty=line.qty, price_snapshot=line.price)
        for line in quote.lines
    ])
    if phone and customer.phone != phone:
        customer.phone = phone
        customer.save(update_fields=["phone"])
    return order


@transaction.atomic
def change_status(order_id: int, new_status: str, *, shop=None) -> tuple[Order, bool]:
    """(order, o'zgardimi). Ikki marta bosilganda ikkinchisi o'zgartirmaydi."""
    order = Order.objects.select_for_update(of=("self",)).select_related("shop", "customer", "courier").get(pk=order_id)
    if shop is not None and order.shop_id != shop.pk:
        raise OrderError("Buyurtma topilmadi.")
    if new_status not in TRANSITIONS[order.status]:
        return order, False
    if new_status == Order.Status.DELIVERING:
        if order.delivery_type != Order.DeliveryType.DELIVERY:
            return order, False
        order.courier = cafe.pick_courier(order.shop)
    order.status = new_status
    order.save()
    return order, True


def cancel_by_customer(order_id: int, customer: Customer) -> tuple[Order, bool]:
    order = Order.objects.get(pk=order_id, customer=customer)
    if order.status != Order.Status.NEW or order.payment_status == Order.PaymentStatus.PAID:
        raise OrderError("Bu buyurtmani endi bekor qilib bo'lmaydi. Do'kon bilan bog'laning.")
    return change_status(order.pk, Order.Status.CANCELLED, shop=order.shop)


STATUS_ICON = {"new": "🆕", "accepted": "✅", "delivering": "🚚", "done": "✔️", "cancelled": "❌"}


def render_order(order: Order, *, staff: bool = False) -> str:
    """Buyurtma kartochkasi (HTML). staff=True bo'lsa mijoz ma'lumotlari ham chiqadi."""
    shop = order.shop
    e = html.escape
    lines = [f"🧾 <b>Buyurtma #{order.number}</b> — {STATUS_ICON[order.status]} {order.get_status_display()}", ""]
    for item in order.items.all():
        lines.append(f"• {e(item.name_snapshot)} ×{item.qty} — {fmt_money(item.line_total, shop.currency)}")
    lines.append("")
    lines.append(f"Mahsulotlar: {fmt_money(order.subtotal, shop.currency)}")
    if order.delivery_type == Order.DeliveryType.DELIVERY:
        lines.append(f"Yetkazish: {fmt_money(order.delivery_fee, shop.currency)}")
    lines.append(f"<b>Jami: {fmt_money(order.total, shop.currency)}</b>")
    paid = "✅ to'langan" if order.payment_status == Order.PaymentStatus.PAID else "⏳ to'lanmagan"
    pay = order.get_payment_method_display()
    lines.append(f"To'lov: {pay}" + ("" if order.payment_method == Order.PaymentMethod.CASH else f" ({paid})"))
    lines.append(f"Turi: {order.get_delivery_type_display()}")
    if order.address:
        lines.append(f"📍 {e(order.address)}")
    if staff:
        customer = order.customer
        who = e(customer.full_name or str(customer.tg_id))
        if customer.username:
            who += f" (@{e(customer.username)})"
        lines.append(f"👤 {who}")
        if order.phone:
            lines.append(f"📞 {e(order.phone)}")
        if order.lat is not None and order.lng is not None:
            lines.append(f'🗺 <a href="https://maps.google.com/?q={order.lat},{order.lng}">Xaritada ochish</a>')
        if order.courier:
            lines.append(f"🛵 Kuryer: {e(order.courier.name)}")
    if order.comment:
        lines.append(f"💬 {e(order.comment)}")
    return "\n".join(lines)
