from django.contrib import admin

from apps.shops.admin import ShopScopedAdminMixin

from .models import Category, Product


@admin.register(Category)
class CategoryAdmin(ShopScopedAdminMixin, admin.ModelAdmin):
    list_display = ("name", "shop", "position", "is_active")
    list_editable = ("position", "is_active")
    list_filter = ("shop",)


@admin.register(Product)
class ProductAdmin(ShopScopedAdminMixin, admin.ModelAdmin):
    list_display = ("name", "category", "price", "is_available", "position")
    list_editable = ("price", "is_available", "position")
    list_filter = ("shop", "category", "is_available")
    search_fields = ("name",)

    def save_model(self, request, obj, form, change):
        if "image" in form.changed_data:
            obj.tg_file_id = ""  # rasm almashganda eski Telegram file_id yaroqsiz
        super().save_model(request, obj, form, change)
