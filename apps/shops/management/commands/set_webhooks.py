from django.core.management.base import BaseCommand

from apps.shops.models import Shop
from apps.shops.services import setup_webhook


class Command(BaseCommand):
    help = "Barcha faol do'konlar botlari uchun webhook'ni qayta o'rnatadi (domen o'zgargandan keyin)."

    def handle(self, *args, **options):
        for shop in Shop.objects.filter(is_active=True):
            try:
                self.stdout.write(self.style.SUCCESS(f"{shop.name}: @{setup_webhook(shop)}"))
            except Exception as exc:
                self.stdout.write(self.style.ERROR(f"{shop.name}: {exc}"))
