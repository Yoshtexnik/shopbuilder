import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl


def check_init_data(init_data: str, bot_token: str, max_age: int = 86400) -> tuple[dict | None, str]:
    """(foydalanuvchi, sabab). Sabab: ok, empty, no_hash, bad_hash, expired, no_user."""
    if not init_data:
        return None, "empty"
    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = pairs.pop("hash", None)
    if not received_hash:
        return None, "no_hash"
    check_string = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received_hash):
        return None, "bad_hash"
    try:
        if time.time() - int(pairs.get("auth_date", "0")) > max_age:
            return None, "expired"
        user = json.loads(pairs["user"])
    except (KeyError, ValueError):
        return None, "no_user"
    if not isinstance(user, dict) or "id" not in user:
        return None, "no_user"
    return user, "ok"


def validate_init_data(init_data: str, bot_token: str, max_age: int = 86400) -> dict | None:
    """Telegram Mini App initData imzosini tekshiradi va foydalanuvchini qaytaradi (yoki None)."""
    return check_init_data(init_data, bot_token, max_age)[0]
