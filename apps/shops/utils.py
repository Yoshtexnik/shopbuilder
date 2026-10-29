from decimal import Decimal


class OrderError(Exception):
    """Foydalanuvchiga ko'rsatiladigan buyurtma xatosi."""


def fmt_money(amount, currency: str = "so'm") -> str:
    amount = Decimal(amount)
    if amount == amount.to_integral_value():
        text = f"{int(amount):,}".replace(",", " ")
    else:
        text = f"{amount:,.2f}".replace(",", " ")
    return f"{text} {currency}".strip()
