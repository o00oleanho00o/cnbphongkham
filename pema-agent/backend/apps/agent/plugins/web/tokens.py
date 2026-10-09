"""Login tokens: JWT signed with HS256 by the plugin's own key, naming the account (``sub``) and its
``token_version`` (``ver``), so a password change ends every older login."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Final

import jwt

ISSUER: Final = "pema-agent"
ALGORITHM: Final = "HS256"


def issue(key: str, email: str, version: int, now: datetime, lifetime: timedelta) -> tuple[str, datetime]:
    expires = now + lifetime
    claims: dict[str, Any] = {"sub": email, "ver": version, "iss": ISSUER, "iat": now, "exp": expires}
    return jwt.encode(claims, key, algorithm=ALGORITHM), expires


def read(key: str, token: str) -> tuple[str, int] | None:
    """The account and version of a valid, unexpired token; None for anything else."""
    try:
        claims = jwt.decode(
            token, key, algorithms=[ALGORITHM], issuer=ISSUER, options={"require": ["sub", "exp", "iat"]}
        )
    except jwt.PyJWTError:
        return None
    email, version = claims.get("sub"), claims.get("ver")
    if not isinstance(email, str) or not isinstance(version, int):
        return None
    return email, version
