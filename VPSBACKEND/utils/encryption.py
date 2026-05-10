import os
import base64
from cryptography.fernet import Fernet

AES_KEY = os.getenv("AES_KEY")  # 32-byte key


def _get_cipher():
    if not AES_KEY:
        raise RuntimeError("AES_KEY not set in environment")
    key = base64.urlsafe_b64encode(AES_KEY.encode()[:32].ljust(32, b"0"))
    return Fernet(key)


def encrypt(data: str) -> str:
    return _get_cipher().encrypt(data.encode()).decode()


def decrypt(data: str) -> str:
    return _get_cipher().decrypt(data.encode()).decode()
