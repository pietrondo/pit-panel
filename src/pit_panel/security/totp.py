from typing import cast

import pyotp


def generate_totp_secret() -> str:
    return cast(str, pyotp.random_base32())


def get_totp_uri(secret: str, username: str, issuer: str = "pit-panel") -> str:
    return cast(
        str,
        pyotp.totp.TOTP(secret).provisioning_uri(
            name=username,
            issuer_name=issuer,
        ),
    )


def verify_totp(secret: str, code: str) -> bool:
    totp = pyotp.TOTP(secret)
    return cast(bool, totp.verify(code))
