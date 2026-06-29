import hashlib
from typing import cast

import bcrypt

from pit_panel.config import Settings


def hash_password(password: str, settings: Settings) -> str:
    return cast(str, bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt(rounds=settings.bcrypt_cost),
    ).decode("utf-8"))


def verify_password(password: str, password_hash: str) -> bool:
    return cast(bool, bcrypt.checkpw(
        password.encode("utf-8"),
        password_hash.encode("utf-8"),
    ))


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
