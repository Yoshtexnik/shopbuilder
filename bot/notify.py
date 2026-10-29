"""Sinxron kontekstdan (admin, to'lov webhooklari, Mini App) bot orqali xabar yuborish."""
import logging
from collections.abc import Awaitable, Callable

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from asgiref.sync import async_to_sync

logger = logging.getLogger(__name__)


def make_bot(token: str) -> Bot:
    return Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))


def run_with_bot(shop, func: Callable[[Bot], Awaitable[None]]) -> None:
    """Qisqa muddatli Bot ochadi, func'ni bajaradi, sessiyani yopadi. Xatolar yutiladi va logga yoziladi."""

    async def runner():
        bot = make_bot(shop.bot_token)
        try:
            await func(bot)
        except Exception:
            logger.exception("Bot orqali xabar yuborishda xato (shop=%s)", shop.pk)
        finally:
            await bot.session.close()

    async_to_sync(runner)()
