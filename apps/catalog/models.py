from django.core.exceptions import ValidationError
from django.db import models

from apps.shops.models import ShopOwned


class Category(ShopOwned):
    name = models.CharField("Nomi", max_length=80)
    position = models.PositiveSmallIntegerField("Tartib", default=0)
    is_active = models.BooleanField("Faol", default=True)

    class Meta:
        verbose_name = "Kategoriya"
        verbose_name_plural = "Kategoriyalar"
        ordering = ["position", "id"]

    def __str__(self) -> str:
        return self.name


class Product(ShopOwned):
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="products", verbose_name="Kategoriya")
    name = models.CharField("Nomi", max_length=120)
    description = models.TextField("Tavsif", blank=True)
    price = models.DecimalField("Narxi", max_digits=12, decimal_places=2)
    image = models.ImageField("Rasm", upload_to="products/", blank=True)
    # Telegram file_id bot'ga xos: har do'kon o'z boti bilan, shuning uchun mahsulotda saqlash to'g'ri.
    tg_file_id = models.CharField(max_length=255, blank=True, editable=False)
    position = models.PositiveSmallIntegerField("Tartib", default=0)
    is_available = models.BooleanField("Sotuvda", default=True)

    class Meta:
        verbose_name = "Mahsulot"
        verbose_name_plural = "Mahsulotlar"
        ordering = ["position", "id"]

    def __str__(self) -> str:
        return self.name

    def clean(self):
        if self.category_id and self.shop_id and self.category.shop_id != self.shop_id:
            raise ValidationError({"category": "Kategoriya boshqa do'konga tegishli."})
        if self.shop_id and not self.pk:
            plan = self.shop.plan
            if plan and Product.objects.filter(shop_id=self.shop_id).count() >= plan.max_products:
                raise ValidationError(f"Tarifingizda {plan.max_products} tagacha mahsulot mumkin. Tarifni yangilang.")
