import hashlib

import bcrypt
from cryptography.fernet import Fernet

from pit_panel.config import Settings


def hash_password(password: str, settings: Settings) -> str:
    return bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt(rounds=settings.bcrypt_cost),
    ).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(
        password.encode("utf-8"),
        password_hash.encode("utf-8"),
    )


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def get_fernet(settings: Settings) -> Fernet:
    key = settings.secret_key.encode("utf-8")
    if len(key) < 32:
        key = hashlib.sha256(key).digest()
    b64_key = __import__("base64").urlsafe_b64encode(key.ljust(32, b"\0")[:32])
    return Fernet(b64_key)


def encrypt_value(plain: str, settings: Settings) -> str:
    fernet = get_fernet(settings)
    return fernet.encrypt(plain.encode("utf-8")).decode("utf-8")


def decrypt_value(encrypted: str, settings: Settings) -> str:
    fernet = get_fernet(settings)
    return fernet.decrypt(encrypted.encode("utf-8")).decode("utf-8")
