"""Who may call this service, and how it proves itself to the agent.

Two things, kept apart:

* the connector key (docs/CONNECTOR-PROTOCOL.md, section 1): ``sign`` for what this service sends to the agent,
  ``verify`` for what the agent sends here;
* the staff token of the web in front (the admin routes and the UI): a dashboard login of the agent, checked by
  the agent (``AgentLogins``).
"""

from __future__ import annotations

import hashlib
import hmac
import time
from collections.abc import Callable, Mapping
from typing import Any, Final

import httpx
from fastapi import HTTPException, Request, status

CONNECTOR_HEADER: Final = "x-connector"
TIMESTAMP_HEADER: Final = "x-timestamp"
SIGNATURE_HEADER: Final = "x-signature"
TOLERANCE_S: Final = 300

FETCH_TIMEOUT_S: Final = 5.0


def _digest(key: str, timestamp: str, method: str, path: str, body: bytes) -> str:
    message = f"{timestamp}\n{method.upper()}\n{path}\n".encode() + body
    return hmac.new(key.encode("utf-8"), message, hashlib.sha256).hexdigest()


def sign(
    key: str, connector: str, method: str, path: str, body: bytes = b"", *, now: Callable[[], float] = time.time
) -> dict[str, str]:
    """The three headers of a request: ``HMAC-SHA256(key, timestamp \\n METHOD \\n path \\n body)`` in hex.
    ``path`` is the path as the receiver sees it, without the query."""
    timestamp = str(int(now()))
    return {
        "X-Connector": connector,
        "X-Timestamp": timestamp,
        "X-Signature": _digest(key, timestamp, method, path, body),
    }


def verify(
    key: str,
    connector: str,
    headers: Mapping[str, str],
    method: str,
    path: str,
    body: bytes = b"",
    *,
    now: Callable[[], float] = time.time,
) -> bool:
    """Constant-time check; False on a missing header, another connector name, a stale timestamp or a wrong
    signature. The caller answers 401 without saying which."""
    lowered = {name.lower(): value for name, value in headers.items()}
    name, timestamp, signature = (lowered.get(h) for h in (CONNECTOR_HEADER, TIMESTAMP_HEADER, SIGNATURE_HEADER))
    if not key or not name or not timestamp or not signature or name != connector:
        return False
    try:
        if abs(now() - int(timestamp)) > TOLERANCE_S:
            return False
    except ValueError:
        return False
    expected = _digest(key, timestamp, method, path, body)
    return hmac.compare_digest(expected.encode("ascii"), signature.strip().lower().encode("utf-8", "ignore"))


class AgentUnavailableError(RuntimeError):
    pass


class AgentLogins:
    """Checks a dashboard login of the agent itself (plugin ``web``), the token is shown
    to the agent's ``/v1/plugins/web/me``, which answers 200 only for an admin login. A good answer is kept for a
    short while (by the token's hash) so a page's calls cost one check; a refused token is never kept."""

    def __init__(
        self,
        agent_url: str,
        *,
        keep_s: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._url = f"{agent_url.rstrip('/')}/v1/plugins/web/me"
        self._keep_s = keep_s
        self._clock = clock
        self._transport = transport
        self._good: dict[str, tuple[str, float]] = {}

    async def check(self, token: str) -> tuple[str, bool] | None:
        digest = hashlib.sha256(token.encode()).hexdigest()
        kept = self._good.get(digest)
        if kept is not None and self._clock() - kept[1] < self._keep_s:
            return kept[0], True
        try:
            async with httpx.AsyncClient(timeout=FETCH_TIMEOUT_S, transport=self._transport) as http:
                answer = await http.get(self._url, headers={"Authorization": f"Bearer {token}"})
        except httpx.HTTPError as err:
            raise AgentUnavailableError(f"the agent at {self._url} cannot be reached") from err
        if answer.status_code in (401, 403, 404):
            self._good.pop(digest, None)
            return None
        if answer.status_code != 200:
            raise AgentUnavailableError(f"the agent at {self._url} answered {answer.status_code}")
        body: object = answer.json()
        email = body.get("email") if isinstance(body, dict) else None
        if not isinstance(email, str) or not email:
            return None
        if len(self._good) > 500:
            self._good.clear()
        self._good[digest] = (email, self._clock())
        return email, True


def require_admin(tokens: AgentLogins) -> Callable[[Request], Any]:
    """A FastAPI dependency: 401 without a good admin token, 503 when the agent cannot be asked."""

    async def dependency(request: Request) -> str:
        scheme, _, token = request.headers.get("authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Cần đăng nhập")
        try:
            checked = await tokens.check(token.strip())
        except AgentUnavailableError:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Không hỏi được agent để kiểm đăng nhập") from None
        if checked is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Cần đăng nhập")
        if not checked[1]:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Cần quyền quản trị")
        return checked[0]

    return dependency
