"""Who may call this service, and how it proves itself to the agent.

Two things, kept apart:

* the connector key (docs/CONNECTOR-PROTOCOL.md, section 1): ``sign`` for what this service sends to the agent,
  ``verify`` for what the agent sends here;
* the staff SSO token of the clinic web (the admin routes and the UI): a JWT of the CRM checked with its public
  keys. Modelled on backend/apps/agent/plugin_kit/jwks.py (``KeySet``) and backend/apps/agent/plugins/sso
  (the checks); copied, not imported. Only asymmetric signatures; ``scope`` must hold ``admin``; a token meant
  for another audience (the CRM's events, ``pema-agent-events``) never opens anything here.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import math
import time
from collections.abc import Callable, Mapping
from typing import Any, Final, cast

import httpx
import jwt
from fastapi import HTTPException, Request, status

CONNECTOR_HEADER: Final = "x-connector"
TIMESTAMP_HEADER: Final = "x-timestamp"
SIGNATURE_HEADER: Final = "x-signature"
TOLERANCE_S: Final = 300

ALGORITHMS: Final = frozenset({"EdDSA", "ES256", "RS256"})
LEEWAY_S: Final = 30
"""Clock difference allowed between the CRM and this machine."""
ADMIN_SCOPE: Final = "admin"
EVENTS_AUDIENCE: Final = "pema-agent-events"
FETCH_TIMEOUT_S: Final = 5.0
MAX_AGE_S: Final = 3600.0
RETRY_AFTER_S: Final = 30.0

logger = logging.getLogger(__name__)


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


class KeysUnavailableError(RuntimeError):
    pass


class KeySet:
    """The CRM's public keys (a JWKS document), fetched over HTTP and kept in memory. A key id not held makes
    one fetch, at most every ``retry_after_s``, so made-up key ids cannot make the service hammer the CRM;
    while the CRM cannot be reached the keys already held keep working."""

    def __init__(
        self,
        url: str,
        *,
        max_age_s: float = MAX_AGE_S,
        retry_after_s: float = RETRY_AFTER_S,
        clock: Callable[[], float] = time.monotonic,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._url = url
        self._max_age_s = max_age_s
        self._retry_after_s = retry_after_s
        self._clock = clock
        self._transport = transport
        self._keys: dict[str, jwt.PyJWK] = {}
        self._fetched_at: float | None = None
        self._tried_at: float | None = None
        self._failed = False
        self._lock = asyncio.Lock()

    async def key(self, kid: str) -> jwt.PyJWK | None:
        """The key of ``kid``; None when the CRM does not publish it."""
        if kid in self._keys and self._age(self._fetched_at) < self._max_age_s:
            return self._keys[kid]
        async with self._lock:
            if self._age(self._tried_at) >= self._retry_after_s:
                await self._refresh()
        if kid not in self._keys and self._failed:
            raise KeysUnavailableError(f"the public keys at {self._url} cannot be read")
        return self._keys.get(kid)

    async def _refresh(self) -> None:
        self._tried_at = self._clock()
        try:
            self._keys = await self._fetch()
        except (httpx.HTTPError, ValueError, jwt.PyJWTError) as err:
            self._failed = True
            logger.warning("cannot read the public keys at %s: %s", self._url, err)
            return
        self._failed = False
        self._fetched_at = self._tried_at

    async def _fetch(self) -> dict[str, jwt.PyJWK]:
        async with httpx.AsyncClient(timeout=FETCH_TIMEOUT_S, transport=self._transport) as http:
            response = await http.get(self._url, headers={"Accept": "application/json"})
        response.raise_for_status()
        document: object = response.json()
        if not isinstance(document, dict):
            raise ValueError("not a JWKS document")
        found = jwt.PyJWKSet.from_dict(cast("dict[str, Any]", document))
        return {k.key_id: k for k in found.keys if k.key_id and k.public_key_use in (None, "sig")}

    def _age(self, at: float | None) -> float:
        return math.inf if at is None else self._clock() - at


class StaffTokens:
    """Checks the clinic web's SSO token. ``jwks_url`` empty: no token is ever accepted (the admin routes
    answer 503, so the missing setting is seen)."""

    def __init__(self, issuer: str, audience: str, jwks_url: str, *, keys: KeySet | None = None) -> None:
        self._issuer = issuer
        self._audience = audience
        self._keys = keys if keys is not None else (KeySet(jwks_url) if jwks_url else None)

    @property
    def configured(self) -> bool:
        return self._keys is not None

    async def check(self, token: str) -> tuple[str, bool] | None:
        """(subject, holds the ``admin`` scope) of a valid token; None for anything that is not one."""
        if self._keys is None or token.count(".") != 2:
            return None
        try:
            header = jwt.get_unverified_header(token)
            unverified = jwt.decode(token, options={"verify_signature": False})
        except jwt.PyJWTError:
            return None
        algorithm, kid = header.get("alg"), header.get("kid")
        if unverified.get("iss") != self._issuer or algorithm not in ALGORITHMS or not isinstance(kid, str):
            return None
        if unverified.get("aud") == EVENTS_AUDIENCE:
            return None
        key = await self._keys.key(kid)
        if key is None or key.algorithm_name != algorithm:
            return None
        try:
            claims = jwt.decode(
                token,
                key.key,
                algorithms=[algorithm],
                audience=self._audience,
                issuer=self._issuer,
                leeway=LEEWAY_S,
                options={"require": ["iss", "aud", "sub", "exp", "iat"]},
            )
        except jwt.PyJWTError:
            return None
        subject, scope = claims.get("sub"), claims.get("scope")
        if not isinstance(subject, str) or not subject:
            return None
        return subject, isinstance(scope, str) and ADMIN_SCOPE in scope.split()


def require_admin(tokens: StaffTokens) -> Callable[[Request], Any]:
    """A FastAPI dependency: 401 without a good admin token, 503 when the CRM's keys cannot be read or are not
    configured."""

    async def dependency(request: Request) -> str:
        if not tokens.configured:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "CRM_JWKS_URL chưa được cấu hình")
        scheme, _, token = request.headers.get("authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Cần đăng nhập")
        try:
            checked = await tokens.check(token.strip())
        except KeysUnavailableError:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Không đọc được khóa của CRM") from None
        if checked is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Cần đăng nhập")
        if not checked[1]:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Cần quyền quản trị")
        return checked[0]

    return dependency
