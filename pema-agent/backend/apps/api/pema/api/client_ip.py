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

Pema addition (trusted proxies, SEC-41 follow-up): the original trusted the rightmost entry from ANY peer,
which is only safe when nothing but the proxy can reach the app. Here ``X-Forwarded-For`` is honoured only
when the socket peer itself is in ``trusted_proxies`` (``PEMA_TRUSTED_PROXIES``: IPs or CIDRs, comma
separated; in compose the fixed address of the Caddy container). The chain is then walked from the right,
skipping entries that are trusted proxies too (a second hop such as a CDN in front of Caddy), and the first
other entry is the client. ``behind_proxy=True`` with an EMPTY list trusts nobody: a proxy flag without a
proxy address would otherwise let any host that can reach the port forge its rate-limit key.
"""

from __future__ import annotations

from collections.abc import Iterable
from ipaddress import IPv4Network, IPv6Network, ip_address, ip_network

from starlette.requests import Request

type ProxyNetwork = IPv4Network | IPv6Network


def parse_trusted_proxies(raw: str) -> tuple[ProxyNetwork, ...]:
    """``"172.29.80.2, 10.0.0.0/8"`` -> networks. A malformed entry raises ``ValueError`` (fail at startup
    rather than silently trusting less or more than the operator meant)."""
    return tuple(ip_network(entry.strip(), strict=False) for entry in raw.split(",") if entry.strip())


def resolve_client_ip(
    request: Request,
    *,
    behind_proxy: bool = False,
    trusted_proxies: Iterable[ProxyNetwork] = (),
) -> str:
    peer = _socket_address(request)
    networks = tuple(trusted_proxies)
    if behind_proxy and peer is not None and _is_trusted(peer, networks):
        forwarded = _client_from_chain(request.headers.get("x-forwarded-for"), networks)
        if forwarded:
            return forwarded
    return peer or "unknown"


def rightmost_forwarded_for(header: str | None) -> str | None:
    """Separate so it can be tested without a request."""
    entries = _entries(header)
    return entries[-1] if entries else None


def _entries(header: str | None) -> list[str]:
    return [entry.strip() for entry in (header or "").split(",") if entry.strip()]


def _client_from_chain(header: str | None, networks: tuple[ProxyNetwork, ...]) -> str | None:
    """Walk the chain right to left; the first entry that is not one of our proxies is the client. An entry
    that is not an IP address ends the walk with no answer (the caller falls back to the socket address)."""
    for entry in reversed(_entries(header)):
        if not _is_ip(entry):
            return None
        if not _is_trusted(entry, networks):
            return entry
    return None


def _is_ip(value: str) -> bool:
    try:
        ip_address(value)
    except ValueError:
        return False
    return True


def _is_trusted(value: str, networks: tuple[ProxyNetwork, ...]) -> bool:
    try:
        address = ip_address(value)
    except ValueError:
        return False
    return any(address in network for network in networks if address.version == network.version)


def _socket_address(request: Request) -> str | None:
    # An in-process test client (ASGITransport) has no real socket: ``request.client`` may be None.
    return request.client.host if request.client else None
