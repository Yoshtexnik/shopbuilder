from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand
from asgiref.sync import async_to_sync

ALLOWED_UPDATES = ["message", "callback_query"]


async def asetup_webhook(shop) -> str:
    """Botni tekshiradi, webhook va buyruqlarni o'rnatadi. Bot username'ini qaytaradi."""
    bot = Bot(token=shop.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    try:
        me = await bot.get_me()
        await bot.set_webhook(
            url=shop.webhook_url,
            secret_token=shop.webhook_secret,
            allowed_updates=ALLOWED_UPDATES,
            drop_pending_updates=False,
        )
        await bot.set_my_commands([
            BotCommand(command="start", description="Boshlash"),
            BotCommand(command="chatid", description="Chat ID ni ko'rsatish"),
        ])
        return me.username or ""
    finally:
        await bot.session.close()


def setup_webhook(shop) -> str:
    username = async_to_sync(asetup_webhook)(shop)
    if username != shop.bot_username:
        shop.bot_username = username
        shop.save(update_fields=["bot_username"])
    return username
