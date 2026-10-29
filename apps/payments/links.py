import base64
from urllib.parse import urlencode

from django.conf import settings


def _return_url(shop) -> str:
    return f"https://t.me/{shop.bot_username}" if shop.bot_username else settings.BASE_URL


def click_url(order) -> str:
    shop = order.shop
    query = urlencode({
        "service_id": shop.click_service_id,
        "merchant_id": shop.click_merchant_id,
        "amount": f"{order.total:.2f}",
        "transaction_param": order.pk,
        "return_url": _return_url(shop),
    })
    return f"https://my.click.uz/services/pay?{query}"


def payme_url(order) -> str:
    shop = order.shop
    tiyin = int(order.total * 100)
    raw = f"m={shop.payme_merchant_id};ac.order_id={order.pk};a={tiyin};l=uz;c={_return_url(shop)}"
    return "https://checkout.paycom.uz/" + base64.b64encode(raw.encode()).decode()


def pay_url(order) -> str | None:
    if order.payment_status == "paid":
        return None
    if order.payment_method == "click":
        return click_url(order)
    if order.payment_method == "payme":
        return payme_url(order)
    return None
