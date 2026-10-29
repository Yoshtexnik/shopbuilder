from aiogram import BaseMiddleware

from apps.orders.models import Customer


class CustomerMiddleware(BaseMiddleware):
    """Shaxsiy chatdagi foydalanuvchini do'konning mijozi sifatida yuklaydi (guruh a'zolari mijoz bo'lmaydi)."""

    async def __call__(self, handler, event, data):
        user = data.get("event_from_user")
        chat = data.get("event_chat")
        if user and not user.is_bot and chat is not None and chat.type == "private":
            shop = data["shop"]
            customer, created = await Customer.objects.aget_or_create(
                shop=shop, tg_id=user.id,
                defaults={"full_name": user.full_name[:150], "username": (user.username or "")[:64]},
            )
            if not created and (customer.full_name != user.full_name[:150] or customer.username != (user.username or "")[:64]):
                customer.full_name, customer.username = user.full_name[:150], (user.username or "")[:64]
                await customer.asave(update_fields=["full_name", "username"])
            data["customer"] = customer
        return await handler(event, data)
