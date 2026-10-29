import hmac
import json
import logging

from aiogram.types import Update
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt

from apps.shops.models import Shop

from . import loader, texts

logger = logging.getLogger(__name__)


async def _reply_closed(bot, update: Update) -> None:
    if update.callback_query:
        await bot.answer_callback_query(update.callback_query.id, texts.SHOP_CLOSED, show_alert=True)
    elif update.message and update.message.chat.type == "private":
        await bot.send_message(update.message.chat.id, texts.SHOP_CLOSED)


@csrf_exempt
async def webhook(request, shop_id: int, secret: str):
    if request.method != "POST":
        return HttpResponse(status=405)
    shop = await Shop.objects.filter(pk=shop_id, is_active=True).afirst()
    if shop is None or not hmac.compare_digest(shop.webhook_secret, secret):
        return HttpResponse(status=404)
    header = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not hmac.compare_digest(shop.webhook_secret, header):
        return HttpResponse(status=403)
    try:
        payload = json.loads(request.body)
    except ValueError:
        return HttpResponse(status=400)

    bot = await loader.get_bot(shop)
    try:
        update = Update.model_validate(payload, context={"bot": bot})
        if shop.is_paid:
            await loader.dp.feed_update(bot, update, shop=shop)
        else:
            await _reply_closed(bot, update)
    except Exception:
        # Telegram'ga baribir 200 qaytaramiz, aks holda xato update qayta-qayta yuboriladi.
        logger.exception("Update qayta ishlanmadi (shop=%s)", shop.pk)
    return HttpResponse("ok")
