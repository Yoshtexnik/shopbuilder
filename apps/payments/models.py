from django.db import models


class Payment(models.Model):
    """state kodlari Payme bilan bir xil: 1 yaratilgan, 2 bajarilgan, -1/-2 bekor qilingan."""

    class Provider(models.TextChoices):
        CLICK = "click", "Click"
        PAYME = "payme", "Payme"

    CREATED, PERFORMED, CANCELLED, CANCELLED_AFTER = 1, 2, -1, -2

    order = models.ForeignKey("orders.Order", on_delete=models.PROTECT, related_name="payments")
    provider = models.CharField(max_length=10, choices=Provider.choices)
    amount = models.DecimalField("Summa", max_digits=12, decimal_places=2)
    state = models.SmallIntegerField(default=CREATED)
    external_id = models.CharField(max_length=64, db_index=True)
    reason = models.SmallIntegerField(null=True, blank=True)
    payme_time = models.BigIntegerField(default=0)
    create_time_ms = models.BigIntegerField(default=0)
    perform_time_ms = models.BigIntegerField(default=0)
    cancel_time_ms = models.BigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "To'lov"
        verbose_name_plural = "To'lovlar"
        ordering = ["-id"]
        constraints = [models.UniqueConstraint(fields=["provider", "external_id"], name="uniq_payment_external")]

    def __str__(self) -> str:
        return f"{self.provider} #{self.pk} — {self.amount}"
