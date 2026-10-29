from django.contrib import admin, messages

from .models import Plan, Shop
from .services import setup_webhook


class ShopScopedAdminMixin:
    """Sotuvchi faqat o'z do'konlariga tegishli yozuvlarni ko'radi va tahrirlaydi."""

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs if request.user.is_superuser else qs.filter(shop__owner=request.user)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if not request.user.is_superuser:
            related = db_field.related_model
            if related is Shop:
                kwargs["queryset"] = Shop.objects.filter(owner=request.user)
            elif any(f.name == "shop" for f in related._meta.fields):
                kwargs["queryset"] = related.objects.filter(shop__owner=request.user)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def get_changeform_initial_data(self, request):
        initial = super().get_changeform_initial_data(request)
        if not request.user.is_superuser:
            shops = list(Shop.objects.filter(owner=request.user)[:2])
            if len(shops) == 1:
                initial.setdefault("shop", shops[0].pk)
        return initial


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ("name", "price", "days", "max_products", "is_active")


@admin.register(Shop)
class ShopAdmin(admin.ModelAdmin):
    list_display = ("name", "template", "owner", "bot_username", "is_active", "paid_until")
    list_filter = ("template", "is_active")
    search_fields = ("name", "bot_username", "owner__username")
    actions = ["connect_bot", "extend_30_days"]
    readonly_fields = ("bot_username", "webhook_url_display", "webapp_url_display")
    fieldsets = (
        ("Asosiy", {"fields": ("name", "template", "welcome_text", "contact_phone", "currency")}),
        ("Telegram bot", {"fields": ("bot_token", "bot_username", "order_chat_id", "webapp_enabled", "webhook_url_display", "webapp_url_display")}),
        ("To'lov", {
            "fields": ("cash_enabled", "click_service_id", "click_merchant_id", "click_secret_key", "payme_merchant_id", "payme_key"),
            "description": "Click/Payme kabinetida Prepare/Complete (yoki Merchant API) manziliga quyidagi to'lov URL'ni kiriting: "
                           "/pay/click/&lt;do'kon ID&gt;/ va /pay/payme/&lt;do'kon ID&gt;/",
        }),
        ("Tarif", {"fields": ("owner", "plan", "paid_until", "is_active")}),
    )

    @admin.display(description="Webhook URL")
    def webhook_url_display(self, obj):
        return obj.webhook_url if obj.pk else "Saqlagandan keyin ko'rinadi"

    @admin.display(description="Mini App URL")
    def webapp_url_display(self, obj):
        return obj.webapp_url if obj.pk else "Saqlagandan keyin ko'rinadi"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs if request.user.is_superuser else qs.filter(owner=request.user)

    def get_readonly_fields(self, request, obj=None):
        fields = list(super().get_readonly_fields(request, obj))
        if not request.user.is_superuser:
            fields += ["owner", "plan", "paid_until", "is_active"]
        return fields

    def save_model(self, request, obj, form, change):
        if not change and not request.user.is_superuser:
            obj.owner = request.user
        super().save_model(request, obj, form, change)
        if not change or "bot_token" in form.changed_data:
            self._connect(request, obj)

    def _connect(self, request, shop):
        try:
            username = setup_webhook(shop)
            self.message_user(request, f"Bot ulandi: @{username}", messages.SUCCESS)
        except Exception as exc:
            self.message_user(request, f"Botni ulab bo'lmadi (token yoki BASE_URL ni tekshiring): {exc}", messages.ERROR)

    @admin.action(description="Botni qayta ulash (webhook)")
    def connect_bot(self, request, queryset):
        for shop in queryset:
            self._connect(request, shop)

    @admin.action(description="Obunani 30 kunga uzaytirish")
    def extend_30_days(self, request, queryset):
        if not request.user.is_superuser:
            self.message_user(request, "Faqat administrator uzaytira oladi.", messages.ERROR)
            return
        for shop in queryset:
            shop.extend(30)
        self.message_user(request, f"{queryset.count()} ta do'kon uzaytirildi.", messages.SUCCESS)
