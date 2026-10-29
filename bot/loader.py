"""Bitta Dispatcher barcha do'konlarga xizmat qiladi; Bot obyektlari do'kon bo'yicha keshlanadi."""
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.base import BaseStorage
from aiogram.fsm.storage.memory import MemoryStorage
from django.conf import settings

from . import notify
from .handlers import checkout, cart, menu, my_orders, staff, start
from .middleware import CustomerMiddleware

logger = logging.getLogger(__name__)


def build_storage() -> BaseStorage:
    if settings.REDIS_URL:
        from aiogram.fsm.storage.redis import RedisStorage

        return RedisStorage.from_url(settings.REDIS_URL)
    logger.warning("REDIS_URL yo'q: FSM xotirada saqlanadi (faqat dev uchun, qayta ishga tushganda savatlar yo'qoladi).")
    return MemoryStorage()


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher(storage=build_storage())
    dp.message.middleware(CustomerMiddleware())
    dp.callback_query.middleware(CustomerMiddleware())
    # Tartib muhim: asosiy tugmalar (menyu, savat...) holatga bog'liq checkout'dan oldin turadi,
    # shunda buyurtma jarayonida «🍽 Menyu» bosilsa manzil sifatida o'qilmaydi.
    dp.include_routers(start.router, staff.router, menu.router, cart.router, my_orders.router, checkout.router)
    return dp


dp = build_dispatcher()
_bots: dict[int, Bot] = {}


async def get_bot(shop) -> Bot:
    cached = _bots.get(shop.pk)
    if cached is not None and cached.token == shop.bot_token:
        return cached
    if cached is not None:
        await cached.session.close()
    bot = notify.make_bot(shop.bot_token)
    _bots[shop.pk] = bot
    return bot
