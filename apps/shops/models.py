import secrets
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from .fields import EncryptedTextField


def new_webhook_secret() -> str:
    return secrets.token_urlsafe(24)


class Plan(models.Model):
    name = models.CharField("Nomi", max_length=80)
    price = models.DecimalField("Narxi (oyiga)", max_digits=12, decimal_places=2, default=0)
    days = models.PositiveIntegerField("Davomiyligi (kun)", default=30)
    max_products = models.PositiveIntegerField("Mahsulotlar limiti", default=100)
    is_active = models.BooleanField("Faol", default=True)

    class Meta:
        verbose_name = "Tarif"
        verbose_name_plural = "Tariflar"

    def __str__(self) -> str:
        return self.name


class Shop(models.Model):
    class Template(models.TextChoices):
        GENERAL = "general", "Umumiy do'kon"
        CAFE = "cafe", "Kafe / fastfood"

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="shops", verbose_name="Egasi")
    name = models.CharField("Do'kon nomi", max_length=120)
    template = models.CharField("Shablon", max_length=20, choices=Template.choices, default=Template.GENERAL)
    plan = models.ForeignKey(Plan, null=True, blank=True, on_delete=models.SET_NULL, verbose_name="Tarif")

    bot_token = EncryptedTextField("Bot tokeni", help_text="@BotFather bergan token. Bazada shifrlanib saqlanadi.")
    bot_username = models.CharField(max_length=64, blank=True, editable=False)
    webhook_secret = models.CharField(max_length=64, default=new_webhook_secret, editable=False)
    order_chat_id = models.BigIntegerField(
        "Buyurtmalar guruhi ID", null=True, blank=True,
        help_text="Botni guruhga qo'shib /chatid yozing, chiqqan raqamni shu yerga kiriting.",
    )

    contact_phone = models.CharField("Telefon", max_length=20, blank=True)
    welcome_text = models.TextField("Salomlashish matni", blank=True)
    currency = models.CharField("Valyuta belgisi", max_length=10, default="so'm")
    webapp_enabled = models.BooleanField("Mini App yoqilgan", default=True)

    cash_enabled = models.BooleanField("Naqd to'lov", default=True)
    click_service_id = models.CharField("Click service_id", max_length=32, blank=True)
    click_merchant_id = models.CharField("Click merchant_id", max_length=32, blank=True)
    click_secret_key = EncryptedTextField("Click secret key", blank=True, default="")
    payme_merchant_id = models.CharField("Payme merchant_id", max_length=64, blank=True)
    payme_key = EncryptedTextField("Payme kaliti", blank=True, default="")

    paid_until = models.DateField("To'langan sana", null=True, blank=True)
    is_active = models.BooleanField("Faol", default=True)
    order_counter = models.PositiveIntegerField(default=0, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Do'kon"
        verbose_name_plural = "Do'konlar"

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if self._state.adding and not self.paid_until:
            self.paid_until = timezone.localdate() + timedelta(days=settings.TRIAL_DAYS)
        super().save(*args, **kwargs)

    @property
    def is_paid(self) -> bool:
        return bool(self.paid_until and self.paid_until >= timezone.localdate())

    @property
    def webhook_url(self) -> str:
        return f"{settings.BASE_URL}/webhook/{self.pk}/{self.webhook_secret}/"

    @property
    def webapp_url(self) -> str:
        return f"{settings.BASE_URL}/app/{self.pk}/"

    @property
    def click_enabled(self) -> bool:
        return bool(self.click_service_id and self.click_merchant_id and self.click_secret_key)

    @property
    def payme_enabled(self) -> bool:
        return bool(self.payme_merchant_id and self.payme_key)

    def extend(self, days: int) -> None:
        start = max(self.paid_until or timezone.localdate(), timezone.localdate())
        self.paid_until = start + timedelta(days=days)
        self.save(update_fields=["paid_until"])


class ShopOwned(models.Model):
    """Har bir do'konga tegishli model uchun asos (multi-tenant)."""

    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, verbose_name="Do'kon")

    class Meta:
        abstract = True
