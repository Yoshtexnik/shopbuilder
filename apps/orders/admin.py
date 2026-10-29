from django.contrib import admin, messages

from apps.shops.admin import ShopScopedAdminMixin
from apps.shops.utils import OrderError

from .models import Customer, Order, OrderItem
from .services import change_status


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    can_delete = False
    readonly_fields = ("product", "name_snapshot", "qty", "price_snapshot")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Order)
class OrderAdmin(ShopScopedAdminMixin, admin.ModelAdmin):
    list_display = ("number", "shop", "customer", "status", "delivery_type", "payment_method", "payment_status", "total", "created_at")
    list_filter = ("shop", "status", "delivery_type", "payment_method", "payment_status")
    search_fields = ("number", "phone", "customer__full_name")
    date_hierarchy = "created_at"
    inlines = [OrderItemInline]
    actions = ["accept", "start_delivery", "complete", "cancel"]
    readonly_fields = [f.name for f in Order._meta.fields if f.name != "id"]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    def _apply(self, request, queryset, status):
        from bot import flows, notify

        done = 0
        for order in queryset.select_related("shop"):
            try:
                _, changed = change_status(order.pk, status, shop=order.shop)
            except OrderError as exc:
                self.message_user(request, str(exc), messages.ERROR)
                continue
            if changed:
                done += 1
                notify.run_with_bot(order.shop, lambda bot, pk=order.pk: flows.push_status(bot, pk))
        self.message_user(request, f"{done} ta buyurtma yangilandi.", messages.SUCCESS if done else messages.WARNING)

    @admin.action(description="Qabul qilish")
    def accept(self, request, queryset):
        self._apply(request, queryset, Order.Status.ACCEPTED)

    @admin.action(description="Yo'lga chiqdi")
    def start_delivery(self, request, queryset):
        self._apply(request, queryset, Order.Status.DELIVERING)

    @admin.action(description="Bajarildi")
    def complete(self, request, queryset):
        self._apply(request, queryset, Order.Status.DONE)

    @admin.action(description="Bekor qilish")
    def cancel(self, request, queryset):
        self._apply(request, queryset, Order.Status.CANCELLED)


@admin.register(Customer)
class CustomerAdmin(ShopScopedAdminMixin, admin.ModelAdmin):
    list_display = ("full_name", "username", "phone", "tg_id", "shop", "created_at")
    list_filter = ("shop",)
    search_fields = ("full_name", "username", "phone")
    readonly_fields = ("shop", "tg_id", "full_name", "username", "phone", "created_at")

    def has_add_permission(self, request):
        return False
