from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup


async def get_cart(state: FSMContext) -> dict[int, int]:
    data = await state.get_data()
    return {int(k): int(v) for k, v in data.get("cart", {}).items()}


async def set_cart(state: FSMContext, cart: dict[int, int]) -> None:
    await state.update_data(cart={str(k): v for k, v in cart.items() if v > 0})


async def swap(cb: CallbackQuery, bot: Bot, text: str, kb: InlineKeyboardMarkup | None = None) -> None:
    """Xabarni tahrirlaydi; rasmli xabar bo'lsa o'chirib, yangisini yuboradi."""
    try:
        await cb.message.edit_text(text, reply_markup=kb)
    except TelegramBadRequest as exc:
        if "not modified" in str(exc):
            return
        try:
            await cb.message.delete()
        except TelegramBadRequest:
            pass
        await bot.send_message(cb.from_user.id, text, reply_markup=kb)
