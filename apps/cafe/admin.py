from django.contrib import admin

from apps.shops.admin import ShopScopedAdminMixin

from .models import CafeSettings, Courier


@admin.register(CafeSettings)
class CafeSettingsAdmin(ShopScopedAdminMixin, admin.ModelAdmin):
    list_display = ("shop", "opens_at", "closes_at", "min_order_sum", "delivery_base_fee", "delivery_per_km")


@admin.register(Courier)
class CourierAdmin(ShopScopedAdminMixin, admin.ModelAdmin):
    list_display = ("name", "shop", "tg_id", "phone", "is_active")
    list_filter = ("shop", "is_active")
