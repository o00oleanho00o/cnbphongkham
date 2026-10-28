"""HMAC signing shared by both directions of the bridge protocol (plugin -> bridge requests, bridge -> plugin
events).

New module (no zalo-agent source: the original called zca-js in-process). Rules, mirrored by
``bridge/src/auth.ts``:

* headers ``X-Pema-Timestamp`` (unix seconds) and ``X-Pema-Signature`` = lowercase hex
  ``HMAC-SHA256(secret, f"{timestamp}.{raw_body}")``; an empty body signs the empty string;
* verification is constant-time and rejects a timestamp more than ``TOLERANCE_SECONDS`` away from now (replay
  window). The secret is made fresh each time the plugin starts the bridge; it is never logged.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from collections.abc import Callable, Mapping

TIMESTAMP_HEADER = "x-pema-timestamp"
SIGNATURE_HEADER = "x-pema-signature"
TOLERANCE_SECONDS = 300


def compute_signature(secret: str, timestamp: int, body: bytes) -> str:
    message = f"{timestamp}.".encode() + body
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def signed_headers(secret: str, body: bytes, *, now: Callable[[], float] = time.time) -> dict[str, str]:
    """Headers to attach to an outgoing request or event."""
    timestamp = int(now())
    return {
        "X-Pema-Timestamp": str(timestamp),
        "X-Pema-Signature": compute_signature(secret, timestamp, body),
    }


def verify_signature(
    secret: str,
    headers: Mapping[str, str],
    body: bytes,
    *,
    now: Callable[[], float] = time.time,
    tolerance_seconds: int = TOLERANCE_SECONDS,
) -> bool:
    """Constant-time check; ``False`` on any missing header, malformed value, stale timestamp or mismatch."""
    lowered = {key.lower(): value for key, value in headers.items()}
    raw_timestamp = lowered.get(TIMESTAMP_HEADER)
    signature = lowered.get(SIGNATURE_HEADER)
    if not raw_timestamp or not signature or not secret:
        return False
    try:
        timestamp = int(raw_timestamp)
    except ValueError:
        return False
    if abs(now() - timestamp) > tolerance_seconds:
        return False
    expected = compute_signature(secret, timestamp, body)
    return hmac.compare_digest(expected.encode("ascii"), signature.strip().lower().encode("utf-8", "ignore"))
