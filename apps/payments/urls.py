from django.urls import path

from .click import click_view
from .payme import payme_view

urlpatterns = [
    path("click/<int:shop_id>/", click_view, name="click"),
    path("payme/<int:shop_id>/", payme_view, name="payme"),
]
