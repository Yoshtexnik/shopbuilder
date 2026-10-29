from datetime import time
from decimal import Decimal

from django.db import models

from apps.shops.models import Shop, ShopOwned


class CafeSettings(models.Model):
    shop = models.OneToOneField(Shop, on_delete=models.CASCADE, related_name="cafe", verbose_name="Do'kon")
    opens_at = models.TimeField("Ochilish vaqti", default=time(9, 0))
    closes_at = models.TimeField("Yopilish vaqti", default=time(23, 0), help_text="Ochilish bilan bir xil bo'lsa — 24 soat ochiq.")
    closed_message = models.CharField("Yopiq vaqtdagi xabar", max_length=200, blank=True)
    min_order_sum = models.DecimalField("Minimal buyurtma summasi", max_digits=12, decimal_places=2, default=0)
    delivery_enabled = models.BooleanField("Yetkazib berish", default=True)
    pickup_enabled = models.BooleanField("Olib ketish", default=True)
    delivery_base_fee = models.DecimalField("Yetkazish narxi (bazaviy)", max_digits=12, decimal_places=2, default=0)
    delivery_per_km = models.DecimalField("Har bir km uchun", max_digits=12, decimal_places=2, default=0)
    free_delivery_from = models.DecimalField("Shu summadan tekin yetkazish", max_digits=12, decimal_places=2, null=True, blank=True)
    max_distance_km = models.DecimalField("Maksimal masofa (km)", max_digits=6, decimal_places=1, default=Decimal("10"))
    kitchen_lat = models.FloatField("Oshxona kengligi (lat)", null=True, blank=True)
    kitchen_lng = models.FloatField("Oshxona uzunligi (lng)", null=True, blank=True)

    class Meta:
        verbose_name = "Kafe sozlamalari"
        verbose_name_plural = "Kafe sozlamalari"

    def __str__(self) -> str:
        return f"{self.shop} — kafe sozlamalari"


class Courier(ShopOwned):
    name = models.CharField("Ismi", max_length=100)
    tg_id = models.BigIntegerField("Telegram ID", help_text="Kuryer botga /start yozgan bo'lishi kerak. ID ni /chatid beradi.")
    phone = models.CharField("Telefon", max_length=20, blank=True)
    is_active = models.BooleanField("Ishlayapti", default=True)

    class Meta:
        verbose_name = "Kuryer"
        verbose_name_plural = "Kuryerlar"
        constraints = [models.UniqueConstraint(fields=["shop", "tg_id"], name="uniq_courier_per_shop")]

    def __str__(self) -> str:
        return self.name
