import json
import logging
from decimal import Decimal

from django.http import Http404, JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from apps.cafe import services as cafe
from apps.catalog.models import Category, Product
from apps.orders.models import Customer
from apps.orders.services import OrderError, build_quote, create_order, payment_methods
from apps.payments.links import pay_url
from apps.shops.models import Shop

from .auth import validate_init_data

logger = logging.getLogger(__name__)


def _shop(shop_id: int) -> Shop:
    shop = Shop.objects.filter(pk=shop_id, is_active=True, webapp_enabled=True).first()
    if shop is None:
        raise Http404
    return shop


def _json(request) -> dict:
    try:
        data = json.loads(request.body)
        return data if isinstance(data, dict) else {}
    except ValueError:
        return {}


def _cart(data: dict) -> dict[int, int]:
    cart: dict[int, int] = {}
    for row in data.get("items", []):
        try:
            pid, qty = int(row["id"]), int(row["qty"])
        except (KeyError, TypeError, ValueError):
            raise OrderError("Savat noto'g'ri.")
        cart[pid] = cart.get(pid, 0) + qty
    return cart


def _coords(data: dict):
    try:
        lat, lng = data.get("lat"), data.get("lng")
        return (float(lat), float(lng)) if lat is not None and lng is not None else (None, None)
    except (TypeError, ValueError):
        return None, None


def _money(value: Decimal):
    return int(value) if value == value.to_integral_value() else float(value)


@require_GET
def index(request, shop_id: int):
    shop = _shop(shop_id)
    return render(request, "webapp/index.html", {"shop": shop})


@require_GET
def menu(request, shop_id: int):
    shop = _shop(shop_id)
    categories = []
    for category in Category.objects.filter(shop=shop, is_active=True):
        products = [
            {
                "id": p.pk, "name": p.name, "description": p.description, "price": _money(p.price),
                "image": request.build_absolute_uri(p.image.url) if p.image else "",
            }
            for p in Product.objects.filter(shop=shop, category=category, is_available=True)
        ]
        if products:
            categories.append({"id": category.pk, "name": category.name, "products": products})
    info = {"name": shop.name, "currency": shop.currency, "phone": shop.contact_phone,
            "payment_methods": [{"code": str(c), "label": l} for c, l in payment_methods(shop)],
            "delivery_types": [str(t) for t in cafe.available_delivery_types(shop)],
            "is_open": True, "needs_location": False, "hours": ""}
    if shop.template == Shop.Template.CAFE:
        cs = cafe.get_settings(shop)
        info.update(is_open=cafe.is_open(cs), needs_location=cs.kitchen_lat is not None,
                    min_order=_money(cs.min_order_sum), hours=f"{cs.opens_at:%H:%M}–{cs.closes_at:%H:%M}")
    return JsonResponse({"shop": info, "categories": categories})


@csrf_exempt
@require_POST
def quote(request, shop_id: int):
    shop = _shop(shop_id)
    data = _json(request)
    try:
        lat, lng = _coords(data)
        result = build_quote(shop, _cart(data), data.get("delivery_type", "pickup"), lat, lng)
    except OrderError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)
    return JsonResponse({"ok": True, "subtotal": _money(result.subtotal), "delivery_fee": _money(result.delivery_fee),
                         "total": _money(result.total)})


@csrf_exempt
@require_POST
def order(request, shop_id: int):
    shop = _shop(shop_id)
    tg_user = validate_init_data(request.headers.get("X-Telegram-Init-Data", ""), shop.bot_token)
    if tg_user is None:
        return JsonResponse({"ok": False, "error": "Telegram orqali qayta oching."}, status=401)
    data = _json(request)
    full_name = f"{tg_user.get('first_name', '')} {tg_user.get('last_name', '')}".strip()[:150]
    customer, _ = Customer.objects.get_or_create(
        shop=shop, tg_id=int(tg_user["id"]),
        defaults={"full_name": full_name, "username": str(tg_user.get("username", ""))[:64]},
    )
    try:
        lat, lng = _coords(data)
        created = create_order(
            shop=shop, customer=customer, cart=_cart(data), delivery_type=str(data.get("delivery_type", "")),
            payment_method=str(data.get("payment_method", "")), phone=str(data.get("phone", ""))[:20],
            address=str(data.get("address", "")), lat=lat, lng=lng, comment=str(data.get("comment", "")),
        )
    except OrderError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)

    from bot import flows, notify

    notify.run_with_bot(shop, lambda bot: flows.publish_order(bot, created.pk))
    return JsonResponse({"ok": True, "number": created.number, "pay_url": pay_url(created)})
