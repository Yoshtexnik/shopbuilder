import json
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from apps.catalog.models import Product
from apps.orders.models import Order
from apps.shops.models import Shop
from webapp.auth import validate_init_data

from .helpers import TOKEN, make_menu, make_shop, sign_init_data

TG_USER = {"id": 4242, "first_name": "Vali", "username": "vali"}


class WebAppTests(TestCase):
    def setUp(self):
        self.shop = make_shop()
        _, self.lavash, self.cola = make_menu(self.shop)
        self.base = f"/app/{self.shop.pk}"

    def post(self, path, body, init=True):
        headers = {"HTTP_X_TELEGRAM_INIT_DATA": sign_init_data(TOKEN, TG_USER)} if init else {}
        return self.client.post(f"{self.base}{path}", json.dumps(body), content_type="application/json", **headers)

    def test_page_and_menu(self):
        page = self.client.get(f"{self.base}/")
        self.assertContains(page, "Lavash House")
        data = self.client.get(f"{self.base}/api/menu/").json()
        self.assertEqual(data["categories"][0]["products"][0]["price"], 28000)
        self.assertEqual({m["code"] for m in data["shop"]["payment_methods"]}, {"cash", "click", "payme"})
        self.assertTrue(data["shop"]["needs_location"])

    def test_quote_ignores_client_prices_and_checks_distance(self):
        far = self.post("/api/quote/", {"items": [{"id": self.lavash.pk, "qty": 1}], "delivery_type": "delivery", "lat": 41.9, "lng": 69.24}, init=False)
        self.assertEqual(far.status_code, 400)
        ok = self.post("/api/quote/", {"items": [{"id": self.lavash.pk, "qty": 2, "price": 1}], "delivery_type": "pickup"}, init=False).json()
        self.assertEqual(ok["total"], 56000)

    def test_order_requires_valid_signature(self):
        body = {"items": [{"id": self.lavash.pk, "qty": 1}], "delivery_type": "pickup", "payment_method": "cash", "phone": "+998901112233"}
        self.assertEqual(self.post("/api/order/", body, init=False).status_code, 401)
        self.assertIsNone(validate_init_data(sign_init_data(TOKEN, TG_USER, auth_date=1000), TOKEN))
        self.assertIsNone(validate_init_data(sign_init_data("999:other", TG_USER), TOKEN))
        self.assertEqual(Order.objects.count(), 0)

    def test_order_created_and_published(self):
        body = {"items": [{"id": self.lavash.pk, "qty": 1}, {"id": self.cola.pk, "qty": 1}], "delivery_type": "pickup",
                "payment_method": "payme", "phone": "+998901112233", "comment": "Achchiq"}
        with patch("bot.notify.run_with_bot") as run:
            res = self.post("/api/order/", body)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["pay_url"].startswith("https://checkout.paycom.uz/"))
        order = Order.objects.get()
        self.assertEqual((order.total, order.customer.tg_id, order.comment), (Decimal("36000"), 4242, "Achchiq"))
        run.assert_called_once()

    def test_unavailable_product_rejected(self):
        Product.objects.filter(pk=self.cola.pk).update(is_available=False)
        body = {"items": [{"id": self.cola.pk, "qty": 1}], "delivery_type": "pickup", "payment_method": "cash", "phone": "+998901112233"}
        self.assertEqual(self.post("/api/order/", body).status_code, 400)


class AdminTests(TestCase):
    def setUp(self):
        self.shop = make_shop()
        make_menu(self.shop)
        self.admin = get_user_model().objects.create_superuser("root", password="pw")

    def test_every_changelist_renders_for_superuser(self):
        self.client.force_login(self.admin)
        for model in ("shops/shop", "shops/plan", "catalog/category", "catalog/product", "orders/order", "orders/customer",
                      "cafe/cafesettings", "cafe/courier", "payments/payment"):
            self.assertEqual(self.client.get(f"/admin/{model}/").status_code, 200, model)
        self.assertEqual(self.client.get(f"/admin/shops/shop/{self.shop.pk}/change/").status_code, 200)

    def test_seller_sees_only_own_data(self):
        call_command("create_seller", "seller1", "--password", "pw12345!")
        seller = get_user_model().objects.get(username="seller1")
        other_shop = Shop.objects.create(owner=seller, name="Boshqa", bot_token="1:x")
        self.client.force_login(seller)
        shops = self.client.get("/admin/shops/shop/")
        self.assertContains(shops, "Boshqa")
        self.assertNotContains(shops, "Lavash House")
        self.assertEqual(self.client.get(f"/admin/shops/shop/{self.shop.pk}/change/", follow=True).status_code, 200)
        self.assertNotContains(self.client.get(f"/admin/shops/shop/{self.shop.pk}/change/", follow=True), "Lavash House")
        self.assertNotContains(self.client.get("/admin/catalog/product/"), "Lavash mol go'shti")
        # boshqa do'konga mahsulot qo'sha olmaydi (forma querysetida yo'q)
        add_page = self.client.get("/admin/catalog/product/add/")
        self.assertNotContains(add_page, "Lavash House")
        self.assertContains(add_page, "Boshqa")
        self.assertEqual(self.client.get("/admin/shops/plan/").status_code, 403)

    def test_token_is_encrypted_at_rest_and_trial_set(self):
        from django.db import connection

        with connection.cursor() as cur:
            cur.execute("SELECT bot_token, click_secret_key FROM shops_shop WHERE id = %s", [self.shop.pk])
            raw_token, raw_click = cur.fetchone()
        self.assertNotIn("TEST-TOKEN", raw_token)
        self.assertNotIn("clicksecret", raw_click)
        self.shop.refresh_from_db()
        self.assertEqual(self.shop.bot_token, TOKEN)
        self.assertTrue(self.shop.is_paid)
