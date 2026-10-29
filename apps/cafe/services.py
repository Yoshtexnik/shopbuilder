import math
from decimal import ROUND_CEILING, Decimal

from django.utils import timezone

from apps.shops.utils import OrderError

from .models import CafeSettings, Courier


def get_settings(shop) -> CafeSettings:
    return CafeSettings.objects.get_or_create(shop=shop)[0]


def is_open(cs: CafeSettings, now=None) -> bool:
    current = (now or timezone.localtime()).time()
    if cs.opens_at == cs.closes_at:
        return True
    if cs.opens_at < cs.closes_at:
        return cs.opens_at <= current < cs.closes_at
    return current >= cs.opens_at or current < cs.closes_at  # tungi smena


def ensure_open(cs: CafeSettings) -> None:
    if not is_open(cs):
        raise OrderError(cs.closed_message or f"Hozir yopiqmiz. Ish vaqti: {cs.opens_at:%H:%M}–{cs.closes_at:%H:%M}.")


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi, dlmb = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def requires_location(shop) -> bool:
    cs = get_settings(shop)
    return cs.kitchen_lat is not None and cs.kitchen_lng is not None


def available_delivery_types(shop) -> list[str]:
    from apps.orders.models import Order

    if shop.template != shop.Template.CAFE:
        return [Order.DeliveryType.DELIVERY, Order.DeliveryType.PICKUP]
    cs = get_settings(shop)
    types = []
    if cs.delivery_enabled:
        types.append(Order.DeliveryType.DELIVERY)
    if cs.pickup_enabled:
        types.append(Order.DeliveryType.PICKUP)
    return types


def delivery_fee(cs: CafeSettings, delivery_type: str, lat, lng, subtotal: Decimal) -> Decimal:
    if delivery_type == "pickup":
        if not cs.pickup_enabled:
            raise OrderError("Olib ketish hozir mavjud emas.")
        return Decimal("0")
    if not cs.delivery_enabled:
        raise OrderError("Yetkazib berish hozir mavjud emas.")
    fee = cs.delivery_base_fee
    if cs.kitchen_lat is not None and cs.kitchen_lng is not None:
        if lat is None or lng is None:
            raise OrderError("Yetkazish narxini hisoblash uchun lokatsiyani yuboring.")
        km = Decimal(str(round(haversine_km(cs.kitchen_lat, cs.kitchen_lng, lat, lng), 2)))
        if km > cs.max_distance_km:
            raise OrderError(f"Manzilingiz yetkazish hududidan tashqarida ({km} km, maksimal {cs.max_distance_km} km).")
        fee = cs.delivery_base_fee + cs.delivery_per_km * km
        fee = (fee / 100).quantize(Decimal("1"), rounding=ROUND_CEILING) * 100  # 100 so'mgacha yaxlitlash
    if cs.free_delivery_from is not None and subtotal >= cs.free_delivery_from:
        return Decimal("0")
    return Decimal(fee)


def pick_courier(shop):
    """Hozir 'yo'lda' buyurtmasi eng kam faol kuryer."""
    from django.db.models import Count, Q

    return (
        Courier.objects.filter(shop=shop, is_active=True)
        .annotate(load=Count("order", filter=Q(order__status="delivering")))
        .order_by("load", "id")
        .first()
    )
