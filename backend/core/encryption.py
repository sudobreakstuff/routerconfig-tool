import os
import base64

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


_KEY_PATH = os.path.expanduser("~/.routerconfig/encryption.key")
_SALT = b"routerconfig-pro-static-salt-v1"


def _get_or_create_key() -> bytes:
    os.makedirs(os.path.dirname(_KEY_PATH), exist_ok=True)
    if os.path.exists(_KEY_PATH):
        with open(_KEY_PATH, "rb") as f:
            return f.read()
    key = Fernet.generate_key()
    with open(_KEY_PATH, "wb") as f:
        f.write(key)
    return key


def _get_fernet() -> Fernet:
    return Fernet(_get_or_create_key())


def encrypt(plaintext: str) -> str:
    if not plaintext:
        return ""
    f = _get_fernet()
    return f.encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    if not ciphertext:
        return ""
    f = _get_fernet()
    return f.decrypt(ciphertext.encode()).decode()


def encrypt_dict(data: dict, fields: list[str]) -> dict:
    result = data.copy()
    for field in fields:
        if field in result and result[field]:
            result[field] = encrypt(str(result[field]))
    return result


def decrypt_dict(data: dict, fields: list[str]) -> dict:
    result = data.copy()
    for field in fields:
        if field in result and result[field]:
            try:
                result[field] = decrypt(str(result[field]))
            except Exception:
                pass
    return result
