from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import models

_fernet = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        _fernet = Fernet(settings.FIELD_ENCRYPTION_KEY.encode())
    return _fernet


class EncryptedTextField(models.TextField):
    """Bazada shifrlangan holda saqlanadi (bot tokenlari, to'lov kalitlari)."""

    def from_db_value(self, value, expression, connection):
        if not value:
            return value
        try:
            return _get_fernet().decrypt(value.encode()).decode()
        except InvalidToken:
            return value  # shifrlanmagan eski qiymat

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if not value:
            return value
        return _get_fernet().encrypt(value.encode()).decode()
