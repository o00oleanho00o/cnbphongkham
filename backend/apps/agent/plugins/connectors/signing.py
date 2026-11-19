"""HMAC signing of the connector protocol (``docs/CONNECTOR-PROTOCOL.md`` section 1), both directions.

Headers ``X-Connector`` (the connector's name), ``X-Timestamp`` (unix seconds) and ``X-Signature`` = lowercase hex
``HMAC-SHA256(key, timestamp + "\n" + METHOD + "\n" + path + "\n" + body)``. The key is the base64url string, used as
UTF-8 bytes. A receiver refuses a missing header, a wrong signature (compared in constant time) and a timestamp
more than ``TOLERANCE_S`` away from now, all alike.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from collections.abc import Callable, Mapping
from typing import Final

TOLERANCE_S: Final = 300
KEY_BYTES: Final = 32


def new_key() -> str:
    """32 random bytes as base64url without padding."""
    return base64.urlsafe_b64encode(secrets.token_bytes(KEY_BYTES)).rstrip(b"=").decode("ascii")


def signature(key: str, timestamp: int, method: str, path: str, body: bytes) -> str:
    message = f"{timestamp}\n{method.upper()}\n{path}\n".encode() + body
    return hmac.new(key.encode("utf-8"), message, hashlib.sha256).hexdigest()


def signed_headers(
    key: str, connector: str, method: str, path: str, body: bytes, *, now: Callable[[], float] = time.time
) -> dict[str, str]:
    timestamp = int(now())
    return {
        "X-Connector": connector,
        "X-Timestamp": str(timestamp),
        "X-Signature": signature(key, timestamp, method, path, body),
    }


def connector_of(headers: Mapping[str, str]) -> str | None:
    """The name a request claims; what it is worth is decided by ``verify`` with that connector's key."""
    return headers.get("x-connector") or None


def verify(
    key: str,
    headers: Mapping[str, str],
    method: str,
    path: str,
    body: bytes,
    *,
    now: Callable[[], float] = time.time,
) -> bool:
    """Constant-time check; False on any missing header, malformed value, stale timestamp or mismatch."""
    lowered = {k.lower(): v for k, v in headers.items()}
    raw_timestamp = lowered.get("x-timestamp")
    given = lowered.get("x-signature")
    if not raw_timestamp or not given or not key:
        return False
    try:
        timestamp = int(raw_timestamp)
    except ValueError:
        return False
    if abs(now() - timestamp) > TOLERANCE_S:
        return False
    expected = signature(key, timestamp, method, path, body)
    return hmac.compare_digest(expected.encode("ascii"), given.strip().lower().encode("utf-8", "ignore"))
