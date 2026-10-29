from decimal import Decimal

from aiogram.types import Contact, Location
from django.test import TransactionTestCase

from apps.orders.models import Customer, Order
from bot.loader import dp

from .helpers import KITCHEN, STAFF_CHAT, make_bot, make_courier, make_menu, make_shop, user_callback, user_message

USER = 5001


class BotFlowTests(TransactionTestCase):
    def setUp(self):
        self.shop = make_shop()
        self.cat, self.lavash, self.cola = make_menu(self.shop)
        self.bot, self.session = make_bot()

    async def feed(self, update):
        await dp.feed_update(self.bot, update, shop=self.shop)

    async def press(self, data, chat_id=None, user=USER):
        await self.feed(user_callback(user, data, chat_id))

    def last_text(self, chat_id=USER):
        return self.session.texts_to(chat_id)[-1]

    async def fill_cart_and_checkout(self):
        await self.feed(user_message(USER, text="/start"))
        await self.feed(user_message(USER, text="🍽 Menyu"))
        await self.press(f"cat:{self.cat.pk}")
        await self.press(f"prd:{self.lavash.pk}")
        await self.press(f"qty:{self.lavash.pk}:2")
        await self.press(f"add:{self.lavash.pk}:2")
        await self.feed(user_message(USER, text="🧺 Savat"))
        self.assertIn("Lavash mol go'shti ×2", self.last_text())

    async def test_full_delivery_order_with_click(self):
        await self.fill_cart_and_checkout()
        await self.press("cart:checkout:0")
        await self.press("co:type:delivery")
        lat, lng = KITCHEN[0] + 0.02, KITCHEN[1]  # ~2.2 km
        await self.feed(user_message(USER, location=Location(latitude=lat, longitude=lng)))
        self.assertIn("Yetkazish narxi", self.last_text())
        await self.feed(user_message(USER, text="Chilonzor 9, 12-uy"))
        self.assertIn("Telefon", self.last_text())
        await self.feed(user_message(USER, contact=Contact(phone_number="998901234567", first_name="Ali", user_id=USER)))
        await self.press("co:pay:click")
        self.assertIn("Jami", self.session.texts_to(USER)[-2])
        await self.press("co:confirm:")

        order = await Order.objects.select_related("customer").aget(shop=self.shop)
        self.assertEqual(order.subtotal, Decimal("56000"))
        self.assertEqual(order.delivery_fee, Decimal("7300"))  # 5000 + 1000*2.22km -> 100 gacha yaxlitlangan
        self.assertEqual(order.total, Decimal("63300"))
        self.assertEqual((order.payment_method, order.payment_status), ("click", "unpaid"))
        self.assertEqual(order.customer.phone, "+998901234567")
        self.assertEqual(await order.items.acount(), 1)
        # do'kon guruhiga kartochka, mijozga tasdiq + to'lov tugmasi
        self.assertTrue(any("Buyurtma #1" in t for t in self.session.texts_to(STAFF_CHAT)))
        confirmation = [m for m in self.session.sent() if m.chat_id == USER and "qabul qilindi" in m.text][-1]
        self.assertIn("my.click.uz", confirmation.reply_markup.inline_keyboard[0][0].url)
        await order.arefresh_from_db()
        self.assertIsNotNone(order.staff_message_id)

    async def test_staff_buttons_drive_status_and_notify_courier(self):
        courier = await make_courier_async(self.shop)
        await self.fill_cart_and_checkout()
        await self.press("cart:checkout:0")
        await self.press("co:type:delivery")
        await self.feed(user_message(USER, location=Location(latitude=KITCHEN[0] + 0.01, longitude=KITCHEN[1])))
        await self.feed(user_message(USER, text="Yunusobod 4"))
        await self.feed(user_message(USER, contact=Contact(phone_number="+998901234567", first_name="Ali", user_id=USER)))
        await self.press("co:pay:cash")
        await self.press("co:confirm:")
        order = await Order.objects.aget(shop=self.shop)

        # mijoz guruh tugmasini bosolmaydi
        await self.press(f"ost:{order.pk}:accepted", user=USER)
        await order.arefresh_from_db()
        self.assertEqual(order.status, "new")

        for status in ("accepted", "delivering"):
            await self.press(f"ost:{order.pk}:{status}", chat_id=STAFF_CHAT, user=9001)
        await order.arefresh_from_db()
        self.assertEqual(order.status, "delivering")
        self.assertEqual(order.courier_id, courier.pk)
        self.assertTrue(any("yangi buyurtma" in t for t in self.session.texts_to(courier.tg_id)))
        self.assertTrue(self.session.sent(__import__("aiogram").methods.SendLocation))

        # ikki marta bosish holatni buzmaydi
        await self.press(f"ost:{order.pk}:delivering", chat_id=STAFF_CHAT, user=9001)
        await self.press(f"ost:{order.pk}:done", chat_id=STAFF_CHAT, user=9001)
        await order.arefresh_from_db()
        self.assertEqual(order.status, "done")
        self.assertIn("yetkazildi", self.last_text())
        # guruh a'zosi mijoz sifatida yozilmagan
        self.assertFalse(await Customer.objects.filter(tg_id=9001).aexists())

    async def test_out_of_range_and_min_order(self):
        await self.fill_cart_and_checkout()
        await self.press("cart:checkout:0")
        await self.press("co:type:delivery")
        await self.feed(user_message(USER, location=Location(latitude=KITCHEN[0] + 0.5, longitude=KITCHEN[1])))
        self.assertIn("hududidan tashqarida", self.last_text())
        self.assertFalse(await Order.objects.filter(shop=self.shop).aexists())

        # minimal summadan kam savat
        await self.feed(user_message(USER, text="❌ Bekor qilish"))
        await self.press("cart:clear:0")
        await self.press(f"prd:{self.cola.pk}")
        await self.press(f"add:{self.cola.pk}:1")
        await self.press("cart:checkout:0")
        self.assertTrue(any("Minimal buyurtma" in (getattr(m, "text", "") or "") for m in self.session.requests))

    async def test_menu_button_during_checkout_is_not_taken_as_address(self):
        await self.fill_cart_and_checkout()
        await self.press("cart:checkout:0")
        await self.press("co:type:delivery")
        await self.feed(user_message(USER, location=Location(latitude=KITCHEN[0] + 0.01, longitude=KITCHEN[1])))
        await self.feed(user_message(USER, text="🍽 Menyu"))
        self.assertEqual(self.last_text(), "Kategoriyani tanlang:")

    async def test_customer_can_cancel_new_unpaid_order_only(self):
        await self.fill_cart_and_checkout()
        await self.press("cart:checkout:0")
        await self.press("co:type:pickup")
        await self.feed(user_message(USER, contact=Contact(phone_number="+998901234567", first_name="Ali", user_id=USER)))
        await self.press("co:pay:cash")
        await self.press("co:confirm:")
        order = await Order.objects.aget(shop=self.shop)
        self.assertEqual(order.delivery_fee, 0)
        await self.press(f"mo:{order.pk}:cancel")
        await order.arefresh_from_db()
        self.assertEqual(order.status, "cancelled")

    async def test_expired_subscription_is_closed_via_webhook(self):
        from django.test import AsyncClient
        from unittest.mock import patch

        from datetime import timedelta
        from django.utils import timezone

        self.shop.paid_until = timezone.localdate() - timedelta(days=1)
        await self.shop.asave()
        payload = user_message(USER, text="/start").model_dump(mode="json", exclude_none=True, by_alias=True)

        async def fake_get_bot(shop):
            return self.bot

        with patch("bot.loader.get_bot", fake_get_bot):
            client = AsyncClient()
            url = f"/webhook/{self.shop.pk}/{self.shop.webhook_secret}/"
            bad = await client.post(url, payload, content_type="application/json")
            self.assertEqual(bad.status_code, 403)  # Telegram secret header yo'q
            ok = await client.post(url, payload, content_type="application/json",
                                   headers={"X-Telegram-Bot-Api-Secret-Token": self.shop.webhook_secret})
            self.assertEqual(ok.status_code, 200)
            wrong = await client.post(f"/webhook/{self.shop.pk}/wrong/", payload, content_type="application/json")
            self.assertEqual(wrong.status_code, 404)
        self.assertIn("buyurtma qabul qilmayapti", self.last_text())


async def make_courier_async(shop):
    from asgiref.sync import sync_to_async

    return await sync_to_async(make_courier)(shop)
