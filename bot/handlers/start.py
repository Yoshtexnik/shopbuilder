from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from asgiref.sync import sync_to_async

from apps.cafe import services as cafe
from bot import keyboards, texts

router = Router(name="start")


@router.message(CommandStart())
async def start(message: Message, state: FSMContext, shop):
    if message.chat.type != "private":
        return
    await state.clear()
    await message.answer(texts.welcome(shop), reply_markup=keyboards.main_menu(shop))


@router.message(Command("chatid"))
async def chat_id(message: Message):
    """Guruh yoki kuryer ID sini topish uchun (admin panelga kiritiladi)."""
    user_id = message.from_user.id if message.from_user else "—"
    await message.answer(f"Chat ID: <code>{message.chat.id}</code>\nSizning ID: <code>{user_id}</code>")


@router.message(F.text == texts.BTN_CONTACT)
async def contact(message: Message, state: FSMContext, shop):
    await state.set_state(None)
    lines = [f"<b>{shop.name}</b>"]
    if shop.contact_phone:
        lines.append(f"📞 {shop.contact_phone}")
    if shop.template == shop.Template.CAFE:
        cs = await sync_to_async(cafe.get_settings)(shop)
        hours = "24 soat" if cs.opens_at == cs.closes_at else f"{cs.opens_at:%H:%M}–{cs.closes_at:%H:%M}"
        lines.append(f"🕒 Ish vaqti: {hours}")
    await message.answer("\n".join(lines))
