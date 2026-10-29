from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand, CommandError

GROUP = "Sotuvchilar"
PERMISSIONS = [
    ("shops", "add_shop"), ("shops", "change_shop"), ("shops", "view_shop"),
    ("catalog", "add_category"), ("catalog", "change_category"), ("catalog", "delete_category"), ("catalog", "view_category"),
    ("catalog", "add_product"), ("catalog", "change_product"), ("catalog", "delete_product"), ("catalog", "view_product"),
    ("orders", "view_order"), ("orders", "change_order"), ("orders", "view_customer"),
    ("cafe", "add_cafesettings"), ("cafe", "change_cafesettings"), ("cafe", "view_cafesettings"),
    ("cafe", "add_courier"), ("cafe", "change_courier"), ("cafe", "delete_courier"), ("cafe", "view_courier"),
    ("payments", "view_payment"),
]


def seller_group() -> Group:
    group, _ = Group.objects.get_or_create(name=GROUP)
    perms = [Permission.objects.get(content_type__app_label=app, codename=code) for app, code in PERMISSIONS]
    group.permissions.set(perms)
    return group


class Command(BaseCommand):
    help = "Sotuvchi akkaunti (admin panelga kirish huquqi bilan) yaratadi."

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument("--password", required=True)
        parser.add_argument("--email", default="")

    def handle(self, *args, **opts):
        User = get_user_model()
        if User.objects.filter(username=opts["username"]).exists():
            raise CommandError("Bunday foydalanuvchi bor.")
        user = User.objects.create_user(opts["username"], opts["email"], opts["password"], is_staff=True)
        user.groups.add(seller_group())
        self.stdout.write(self.style.SUCCESS(f"Sotuvchi yaratildi: {user.username}"))
