import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message

from apps.catalog.models import Category, Product
from bot import keyboards, texts
from bot.callbacks import AddCB, CatCB, MenuCB, ProdCB, QtyCB
from bot.utils import get_cart, set_cart, swap

logger = logging.getLogger(__name__)
router = Router(name="menu")


async def _categories(shop):
    return [c async for c in Category.objects.filter(shop=shop, is_active=True).order_by("position", "id")]


@router.message(F.text == texts.BTN_MENU)
async def show_menu(message: Message, state: FSMContext, shop):
    await state.set_state(None)
    categories = await _categories(shop)
    if not categories:
        await message.answer(texts.MENU_EMPTY)
        return
    await message.answer("Kategoriyani tanlang:", reply_markup=keyboards.categories_kb(categories))


@router.callback_query(MenuCB.filter(F.act == "cats"))
async def back_to_categories(cb: CallbackQuery, bot: Bot, shop):
    categories = await _categories(shop)
    if not categories:
        await cb.answer(texts.MENU_EMPTY, show_alert=True)
        return
    await swap(cb, bot, "Kategoriyani tanlang:", keyboards.categories_kb(categories))
    await cb.answer()


@router.callback_query(CatCB.filter())
async def show_category(cb: CallbackQuery, callback_data: CatCB, bot: Bot, shop):
    category = await Category.objects.filter(shop=shop, pk=callback_data.id, is_active=True).afirst()
    if category is None:
        await cb.answer("Kategoriya topilmadi", show_alert=True)
        return
    products = [p async for p in Product.objects.filter(shop=shop, category=category, is_available=True).order_by("position", "id")[:80]]
    if not products:
        await cb.answer("Bu kategoriyada hozircha mahsulot yo'q", show_alert=True)
        return
    await swap(cb, bot, f"<b>{category.name}</b>", keyboards.products_kb(products, shop))
    await cb.answer()


async def send_product(bot: Bot, chat_id: int, product: Product, text: str, kb):
    """Rasm bo'lsa file_id bilan, birinchi marta fayl yuklab yuboradi va file_id ni saqlaydi."""
    if product.image:
        candidates = [product.tg_file_id] if product.tg_file_id else []
        candidates.append(None)  # None = diskdagi fayl
        for file_id in candidates:
            try:
                photo = file_id or FSInputFile(product.image.path)
                msg = await bot.send_photo(chat_id, photo, caption=text, reply_markup=kb)
            except (TelegramBadRequest, FileNotFoundError, ValueError) as exc:
                logger.warning("Mahsulot rasmi yuborilmadi (product=%s): %s", product.pk, exc)
                continue
            if msg.photo and msg.photo[-1].file_id != product.tg_file_id:
                product.tg_file_id = msg.photo[-1].file_id
                await product.asave(update_fields=["tg_file_id"])
            return
    await bot.send_message(chat_id, text, reply_markup=kb)


@router.callback_query(ProdCB.filter())
async def show_product(cb: CallbackQuery, callback_data: ProdCB, bot: Bot, shop):
    product = await Product.objects.filter(shop=shop, pk=callback_data.id, is_available=True).afirst()
    if product is None:
        await cb.answer("Mahsulot topilmadi", show_alert=True)
        return
    try:
        await cb.message.delete()
    except TelegramAPIError:
        pass
    await send_product(bot, cb.from_user.id, product, texts.product_card(product, shop), keyboards.product_kb(product, 1, shop))
    await cb.answer()


@router.callback_query(MenuCB.filter(F.act == "back"))
async def back_from_product(cb: CallbackQuery, bot: Bot, shop):
    categories = await _categories(shop)
    try:
        await cb.message.delete()
    except TelegramAPIError:
        pass
    await bot.send_message(cb.from_user.id, "Kategoriyani tanlang:", reply_markup=keyboards.categories_kb(categories))
    await cb.answer()


@router.callback_query(QtyCB.filter())
async def change_qty(cb: CallbackQuery, callback_data: QtyCB, shop):
    product = await Product.objects.filter(shop=shop, pk=callback_data.id).afirst()
    if product is None:
        await cb.answer()
        return
    qty = min(max(callback_data.q, 1), 20)
    try:
        await cb.message.edit_reply_markup(reply_markup=keyboards.product_kb(product, qty, shop))
    except TelegramBadRequest:
        pass  # o'zgarmagan klaviatura
    await cb.answer()


@router.callback_query(AddCB.filter())
async def add_to_cart(cb: CallbackQuery, callback_data: AddCB, state: FSMContext, shop):
    product = await Product.objects.filter(shop=shop, pk=callback_data.id, is_available=True).afirst()
    if product is None:
        await cb.answer("Mahsulot hozir mavjud emas", show_alert=True)
        return
    cart = await get_cart(state)
    cart[product.pk] = min(cart.get(product.pk, 0) + min(max(callback_data.q, 1), 20), 50)
    await set_cart(state, cart)
    try:
        await cb.message.edit_reply_markup(reply_markup=keyboards.after_add_kb())
    except TelegramBadRequest:
        pass
    await cb.answer("✅ Savatga qo'shildi")
