import base64
import hashlib
import json
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from apps.orders.models import Customer, Order
from apps.orders.services import create_order
from apps.payments.models import Payment

from .helpers import make_menu, make_shop


def md5(*parts):
    return hashlib.md5("".join(str(p) for p in parts).encode()).hexdigest()


class PaymentTestBase(TestCase):
    method = "click"

    def setUp(self):
        self.shop = make_shop()
        _, self.lavash, _ = make_menu(self.shop)
        customer = Customer.objects.create(shop=self.shop, tg_id=1, full_name="Ali")
        self.order = create_order(shop=self.shop, customer=customer, cart={self.lavash.pk: 1}, delivery_type="pickup",
                                  payment_method=self.method, phone="+998901234567")
        patcher = patch("apps.payments.services.notify_paid")
        self.notify = patcher.start()
        self.addCleanup(patcher.stop)


class ClickTests(PaymentTestBase):
    method = "click"

    def call(self, action, **extra):
        p = {"click_trans_id": "9001", "service_id": "111", "click_paydoc_id": "5", "merchant_trans_id": str(self.order.pk),
             "amount": "28000.00", "action": str(action), "error": "0", "error_note": "", "sign_time": "2026-10-29 12:00:00"}
        p.update(extra)
        parts = [p["click_trans_id"], p["service_id"], "clicksecret", p["merchant_trans_id"]]
        if action == 1:
            parts.append(p["merchant_prepare_id"])
        parts += [p["amount"], p["action"], p["sign_time"]]
        p.setdefault("sign_string", md5(*parts))
        return self.client.post(f"/pay/click/{self.shop.pk}/", p).json()

    def test_prepare_then_complete_marks_paid(self):
        prepare = self.call(0)
        self.assertEqual(prepare["error"], 0)
        complete = self.call(1, merchant_prepare_id=str(prepare["merchant_prepare_id"]))
        self.assertEqual(complete["error"], 0)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, "paid")
        self.notify.assert_called_once_with(self.order.pk)
        # qayta Complete — "already paid"
        again = self.call(1, merchant_prepare_id=str(prepare["merchant_prepare_id"]))
        self.assertEqual(again["error"], -4)
        self.assertEqual(self.notify.call_count, 1)

    def test_bad_signature_amount_and_order(self):
        self.assertEqual(self.call(0, sign_string="deadbeef")["error"], -1)
        self.assertEqual(self.call(0, amount="1000.00")["error"], -2)
        self.assertEqual(self.call(0, merchant_trans_id="99999")["error"], -5)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, "unpaid")

    def test_click_reports_failure(self):
        prepare = self.call(0)
        res = self.call(1, merchant_prepare_id=str(prepare["merchant_prepare_id"]), error="-5017")
        self.assertEqual(res["error"], -9)
        self.assertEqual(Payment.objects.get().state, Payment.CANCELLED)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, "unpaid")


class PaymeTests(PaymentTestBase):
    method = "payme"

    def rpc(self, method, params, key="paymekey", login="Paycom"):
        auth = "Basic " + base64.b64encode(f"{login}:{key}".encode()).decode()
        res = self.client.post(f"/pay/payme/{self.shop.pk}/", json.dumps({"id": 1, "method": method, "params": params}),
                               content_type="application/json", HTTP_AUTHORIZATION=auth)
        return res.json()

    @property
    def account(self):
        return {"order_id": str(self.order.pk)}

    def test_full_lifecycle(self):
        amount = 2_800_000
        self.assertEqual(self.rpc("CheckPerformTransaction", {"amount": amount, "account": self.account})["result"], {"allow": True})
        created = self.rpc("CreateTransaction", {"id": "tx1", "time": 1700000000000, "amount": amount, "account": self.account})["result"]
        self.assertEqual(created["state"], 1)
        # takroriy Create bir xil natija beradi
        again = self.rpc("CreateTransaction", {"id": "tx1", "time": 1700000000000, "amount": amount, "account": self.account})["result"]
        self.assertEqual(again["create_time"], created["create_time"])
        # shu buyurtma uchun boshqa tranzaksiya — rad etiladi
        other = self.rpc("CreateTransaction", {"id": "tx2", "time": 1700000000001, "amount": amount, "account": self.account})
        self.assertEqual(other["error"]["code"], -31099)

        performed = self.rpc("PerformTransaction", {"id": "tx1"})["result"]
        self.assertEqual(performed["state"], 2)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, "paid")
        self.notify.assert_called_once()
        self.assertEqual(self.rpc("PerformTransaction", {"id": "tx1"})["result"]["state"], 2)
        self.assertEqual(self.notify.call_count, 1)

        check = self.rpc("CheckTransaction", {"id": "tx1"})["result"]
        self.assertEqual((check["state"], check["reason"]), (2, None))
        statement = self.rpc("GetStatement", {"from": 1699999999999, "to": 1700000000002})["result"]["transactions"]
        self.assertEqual([t["id"] for t in statement], ["tx1"])

        cancelled = self.rpc("CancelTransaction", {"id": "tx1", "reason": 5})["result"]
        self.assertEqual(cancelled["state"], -2)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, "unpaid")

    def test_cannot_cancel_after_delivery(self):
        self.rpc("CreateTransaction", {"id": "tx1", "time": 1, "amount": 2_800_000, "account": self.account})
        self.rpc("PerformTransaction", {"id": "tx1"})
        Order.objects.filter(pk=self.order.pk).update(status="done")
        self.assertEqual(self.rpc("CancelTransaction", {"id": "tx1", "reason": 5})["error"]["code"], -31007)

    def test_errors(self):
        self.assertEqual(self.rpc("CheckPerformTransaction", {"amount": 2_800_000, "account": self.account}, key="bad")["error"]["code"], -32504)
        self.assertEqual(self.rpc("CheckPerformTransaction", {"amount": 100, "account": self.account})["error"]["code"], -31001)
        self.assertEqual(self.rpc("CheckPerformTransaction", {"amount": 100, "account": {"order_id": "9999"}})["error"]["code"], -31050)
        self.assertEqual(self.rpc("CheckTransaction", {"id": "nope"})["error"]["code"], -31003)
        self.assertEqual(self.rpc("Whatever", {})["error"]["code"], -32601)
        self.assertEqual(self.client.get(f"/pay/payme/{self.shop.pk}/").json()["error"]["code"], -32300)

    def test_expired_transaction_cancelled_on_perform(self):
        self.rpc("CreateTransaction", {"id": "tx1", "time": 1, "amount": 2_800_000, "account": self.account})
        Payment.objects.update(create_time_ms=1)  # 12 soatdan eski
        res = self.rpc("PerformTransaction", {"id": "tx1"})
        self.assertEqual(res["error"]["code"], -31008)
        payment = Payment.objects.get()
        self.assertEqual((payment.state, payment.reason), (-1, 4))
