from django.db import models

from apps.shops.models import ShopOwned


class Customer(ShopOwned):
    tg_id = models.BigIntegerField("Telegram ID")
    full_name = models.CharField("Ismi", max_length=150, blank=True)
    username = models.CharField("Username", max_length=64, blank=True)
    phone = models.CharField("Telefon", max_length=20, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Mijoz"
        verbose_name_plural = "Mijozlar"
        constraints = [models.UniqueConstraint(fields=["shop", "tg_id"], name="uniq_customer_per_shop")]

    def __str__(self) -> str:
        return self.full_name or str(self.tg_id)


class Order(ShopOwned):
    class Status(models.TextChoices):
        NEW = "new", "Yangi"
        ACCEPTED = "accepted", "Qabul qilindi"
        DELIVERING = "delivering", "Yo'lda"
        DONE = "done", "Bajarildi"
        CANCELLED = "cancelled", "Bekor qilindi"

    class DeliveryType(models.TextChoices):
        DELIVERY = "delivery", "Yetkazib berish"
        PICKUP = "pickup", "Olib ketish"

    class PaymentMethod(models.TextChoices):
        CASH = "cash", "Naqd"
        CLICK = "click", "Click"
        PAYME = "payme", "Payme"

    class PaymentStatus(models.TextChoices):
        UNPAID = "unpaid", "To'lanmagan"
        PAID = "paid", "To'langan"

    number = models.PositiveIntegerField("Raqami")
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="orders", verbose_name="Mijoz")
    status = models.CharField("Holati", max_length=20, choices=Status.choices, default=Status.NEW)
    delivery_type = models.CharField("Turi", max_length=20, choices=DeliveryType.choices)
    payment_method = models.CharField("To'lov usuli", max_length=20, choices=PaymentMethod.choices, default=PaymentMethod.CASH)
    payment_status = models.CharField("To'lov holati", max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.UNPAID)
    subtotal = models.DecimalField("Mahsulotlar", max_digits=12, decimal_places=2)
    delivery_fee = models.DecimalField("Yetkazish", max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField("Jami", max_digits=12, decimal_places=2)
    phone = models.CharField("Telefon", max_length=20, blank=True)
    address = models.TextField("Manzil", blank=True)
    lat = models.FloatField(null=True, blank=True)
    lng = models.FloatField(null=True, blank=True)
    comment = models.TextField("Izoh", blank=True)
    courier = models.ForeignKey("cafe.Courier", null=True, blank=True, on_delete=models.SET_NULL, verbose_name="Kuryer")
    staff_message_id = models.BigIntegerField(null=True, blank=True, editable=False)
    created_at = models.DateTimeField("Vaqti", auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Buyurtma"
        verbose_name_plural = "Buyurtmalar"
        ordering = ["-id"]
        constraints = [models.UniqueConstraint(fields=["shop", "number"], name="uniq_order_number_per_shop")]
        indexes = [models.Index(fields=["shop", "status"])]

    def __str__(self) -> str:
        return f"#{self.number}"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("catalog.Product", null=True, on_delete=models.SET_NULL)
    name_snapshot = models.CharField("Nomi", max_length=120)
    qty = models.PositiveSmallIntegerField("Soni")
    price_snapshot = models.DecimalField("Narxi (buyurtma paytida)", max_digits=12, decimal_places=2)

    class Meta:
        verbose_name = "Buyurtma qatori"
        verbose_name_plural = "Buyurtma qatorlari"

    @property
    def line_total(self):
        return self.price_snapshot * self.qty
