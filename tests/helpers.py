import hashlib
import hmac
import json
import time
from datetime import datetime
from decimal import Decimal
from urllib.parse import urlencode

from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.methods import SendLocation, SendMessage, SendPhoto
from aiogram.types import Chat, Message, Update, User
from django.contrib.auth import get_user_model

from apps.cafe.models import CafeSettings, Courier
from apps.catalog.models import Category, Product
from apps.shops.models import Shop

TOKEN = "123456:TEST-TOKEN"
STAFF_CHAT = -1001234567890
KITCHEN = (41.311081, 69.240562)  # Toshkent markazi


class FakeSession(BaseSession):
    """Telegram'ga chiqmaydi: barcha so'rovlarni yozib boradi."""

    def __init__(self):
        super().__init__()
        self.requests = []
        self._mid = 1000

    async def close(self):
        pass

    async def stream_content(self, *args, **kwargs):
        yield b""

    async def make_request(self, bot, method, timeout=None):
        self.requests.append(method)
        if isinstance(method, (SendMessage, SendPhoto, SendLocation)):
            self._mid += 1
            return Message(message_id=self._mid, date=datetime.now(), chat=Chat(id=method.chat_id, type="private"),
                           text=getattr(method, "text", None))
        return True

    def sent(self, kind=SendMessage):
        return [m for m in self.requests if isinstance(m, kind)]

    def texts_to(self, chat_id):
        return [m.text for m in self.sent() if m.chat_id == chat_id]


def make_bot() -> tuple[Bot, FakeSession]:
    session = FakeSession()
    return Bot(token=TOKEN, session=session), session


def make_shop(**overrides) -> Shop:
    owner = get_user_model().objects.create_user(f"owner{get_user_model().objects.count()}", password="x", is_staff=True)
    data = dict(owner=owner, name="Lavash House", template=Shop.Template.CAFE, bot_token=TOKEN, order_chat_id=STAFF_CHAT,
                webapp_enabled=True, click_service_id="111", click_merchant_id="222", click_secret_key="clicksecret",
                payme_merchant_id="paymeid", payme_key="paymekey")
    data.update(overrides)
    shop = Shop.objects.create(**data)
    CafeSettings.objects.create(shop=shop, opens_at=datetime(2000, 1, 1, 0, 0).time(), closes_at=datetime(2000, 1, 1, 0, 0).time(),
                                min_order_sum=20000, delivery_base_fee=5000, delivery_per_km=1000,
                                kitchen_lat=KITCHEN[0], kitchen_lng=KITCHEN[1], max_distance_km=Decimal("10"))
    return shop


def make_menu(shop):
    cat = Category.objects.create(shop=shop, name="Lavash")
    lavash = Product.objects.create(shop=shop, category=cat, name="Lavash mol go'shti", price=Decimal("28000"), description="Katta")
    cola = Product.objects.create(shop=shop, category=cat, name="Cola 0.5", price=Decimal("8000"))
    return cat, lavash, cola


def make_courier(shop, tg_id=777):
    return Courier.objects.create(shop=shop, name="Aziz", tg_id=tg_id)


_uid = [0]


def _update_id() -> int:
    _uid[0] += 1
    return _uid[0]


def user_message(user_id: int, **fields) -> Update:
    user = User(id=user_id, is_bot=False, first_name="Ali", username="ali")
    msg = Message(message_id=_update_id(), date=datetime.now(), chat=Chat(id=user_id, type="private"), from_user=user, **fields)
    return Update(update_id=_update_id(), message=msg)


def user_callback(user_id: int, data: str, chat_id: int | None = None) -> Update:
    from aiogram.types import CallbackQuery

    user = User(id=user_id, is_bot=False, first_name="Ali", username="ali")
    chat = Chat(id=chat_id or user_id, type="private" if chat_id is None else "supergroup")
    msg = Message(message_id=_update_id(), date=datetime.now(), chat=chat, text="x")
    cb = CallbackQuery(id=str(_update_id()), from_user=user, chat_instance="ci", data=data, message=msg)
    return Update(update_id=_update_id(), callback_query=cb)


def sign_init_data(token: str, user: dict, auth_date: int | None = None) -> str:
    fields = {"auth_date": str(auth_date or int(time.time())), "query_id": "AAH", "user": json.dumps(user)}
    check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)
