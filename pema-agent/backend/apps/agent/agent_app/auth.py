"""Who is calling the gateway. A bearer token is turned into a ``Principal`` by the service's own tokens
(given in code: tests, embedding) or by the authenticators plugins register (``ctx.register_authenticator``:
the ``web`` plugin's logins and API keys). The core keeps no users and reads no token from the environment.

Scopes: ``chat`` reaches the chat routes (``/v1/chat``, ``/v1/ingress``, ``/v1/sessions``, resets); ``admin``
reaches everything under ``/v1/admin`` and the plugins' admin routes.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Final

CHAT: Final = "chat"
ADMIN: Final = "admin"


@dataclass(frozen=True, slots=True)
class Principal:
    subject: str
    """Who it is, for logs and audit (an email, ``apikey:<id>``); never a secret."""
    scopes: frozenset[str]


Authenticator = Callable[[str], Awaitable[Principal | None]]
"""Gets the bearer token as sent; None when it is not one of its own (the next authenticator is asked)."""
