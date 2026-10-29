from django.urls import path

from . import views

urlpatterns = [
    path("<int:shop_id>/", views.index, name="webapp-index"),
    path("<int:shop_id>/api/menu/", views.menu, name="webapp-menu"),
    path("<int:shop_id>/api/quote/", views.quote, name="webapp-quote"),
    path("<int:shop_id>/api/order/", views.order, name="webapp-order"),
]
