from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.shops.models import Shop
from bot import notify


class Command(BaseCommand):
    help = "Obunasi 3 kundan keyin yoki bugun tugaydigan do'konlarga buyurtmalar guruhida eslatma yuboradi (kuniga 1 marta ishga tushiring)."

    def handle(self, *args, **options):
        today = timezone.localdate()
        for days_left in (3, 0):
            for shop in Shop.objects.filter(is_active=True, paid_until=today + timedelta(days=days_left), order_chat_id__isnull=False):
                text = (f"⏰ «{shop.name}» obunasi {days_left} kundan keyin tugaydi." if days_left
                        else f"⏰ «{shop.name}» obunasi bugun tugaydi. Uzaytirmasangiz bot buyurtma qabul qilmay qo'yadi.")
                notify.run_with_bot(shop, lambda bot, s=shop, t=text: bot.send_message(s.order_chat_id, t))
                self.stdout.write(f"{shop.name}: eslatma yuborildi")
