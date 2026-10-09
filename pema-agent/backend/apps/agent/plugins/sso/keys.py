"""The issuer's public keys (a JWKS document), fetched over HTTP and kept in memory.

A key id we do not hold makes one fetch (the issuer rotated its key), at most every ``retry_after_s``, so
tokens with made-up key ids cannot make the service hammer the issuer. While the issuer cannot be reached the
keys already held keep working; a token whose key cannot be looked up raises ``KeysUnavailableError``, which
the gateway answers with 503 rather than counting it as a wrong token.
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from collections.abc import Callable
from typing import Any, Final, cast

import httpx
import jwt

FETCH_TIMEOUT_S: Final = 5.0
MAX_AGE_S: Final = 3600.0
RETRY_AFTER_S: Final = 30.0

logger = logging.getLogger(__name__)


class KeysUnavailableError(RuntimeError):
    pass


class KeySet:
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
        """The key of ``kid``; None when the issuer does not publish it."""
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
