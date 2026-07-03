import secrets
import string


WIFI_CHARS = string.ascii_letters + string.digits + "!@#$%^&*"
ADMIN_CHARS = string.ascii_letters + string.digits + "!@#$%^&*()-_=+[]{}|;:,.<>?"


def generate_password(length: int = 20, charset: str = WIFI_CHARS) -> str:
    while True:
        password = "".join(secrets.choice(charset) for _ in range(length))
        has_upper = any(c.isupper() for c in password)
        has_lower = any(c.islower() for c in password)
        has_digit = any(c.isdigit() for c in password)
        has_special = any(c in "!@#$%^&*" for c in password)
        if has_upper and has_lower and has_digit and has_special:
            return password


def generate_wifi_password() -> str:
    return generate_password(length=20)


def generate_admin_password() -> str:
    return generate_password(length=24, charset=ADMIN_CHARS)


def generate_ssid(prefix: str = "", suffix: str = "") -> str:
    base = prefix or "WiFi"
    rand = secrets.token_hex(3).upper()
    ssid = f"{base}-{rand}"
    if suffix:
        ssid = f"{ssid}-{suffix}"
    return ssid[:32]
