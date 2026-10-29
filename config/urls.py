from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import HttpResponse
from django.urls import include, path

from bot.webhook import webhook

admin.site.site_header = "ShopBuilder — sotuvchi paneli"
admin.site.site_title = "ShopBuilder"
admin.site.index_title = "Do'konni boshqarish"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("webhook/<int:shop_id>/<str:secret>/", webhook, name="bot-webhook"),
    path("pay/", include("apps.payments.urls")),
    path("app/", include("webapp.urls")),
    path("healthz/", lambda request: HttpResponse("ok")),
]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
