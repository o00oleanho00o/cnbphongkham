# ported from: src/server/client-ip.ts
"""IP of the client, used as the login rate-limit key.

Why not read ``X-Forwarded-For`` directly: the client can send that header. Changing its value on each
request would give a fresh rate-limit bucket every time, so a password could be brute-forced without limit.
So without a configured proxy only the socket address is trusted.

Behind a proxy (``PEMA_DASHBOARD_BEHIND_PROXY=true``): Caddy/Nginx APPEND the client IP to the END of an
existing XFF, so the RIGHTMOST entry is the one the proxy wrote; the entries to its left are written by the
client. Taking the leftmost entry, the most common mistake, is exactly the hole.

Forced deviation: Hono ``Context`` / ``getConnInfo`` become Starlette ``Request`` (``request.client``);
``env.DASHBOARD_BEHIND_PROXY`` becomes an explicit argument so the function stays pure and testable.
"""

from __future__ import annotations

from starlette.requests import Request


def resolve_client_ip(request: Request, *, behind_proxy: bool = False) -> str:
    if behind_proxy:
        trusted = rightmost_forwarded_for(request.headers.get("x-forwarded-for"))
        if trusted:
            return trusted
    return _socket_address(request) or "unknown"


def rightmost_forwarded_for(header: str | None) -> str | None:
    """Separate so it can be tested without a request."""
    entries = [entry.strip() for entry in (header or "").split(",") if entry.strip()]
    return entries[-1] if entries else None


def _socket_address(request: Request) -> str | None:
    # An in-process test client (ASGITransport) has no real socket: ``request.client`` may be None.
    return request.client.host if request.client else None
