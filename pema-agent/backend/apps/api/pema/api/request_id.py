"""The ``X-Request-Id`` of a request, cleaned (package G, SECURITY-REVIEW-AI01 SEC-18; no zalo-agent source).

The header comes from the client. It is echoed in every error body, stored in ``clinic.audit_log.request_id``
and shown on the dashboard, so an arbitrary value (megabytes, control characters, markup) is a log-injection
and storage-abuse vector. Only a short token of safe characters is kept; anything else is dropped (the
request is served without an id, never refused).
"""

from __future__ import annotations

import re

_SAFE = re.compile(r"^[A-Za-z0-9._:\-]{1,128}$")


def clean_request_id(value: str | None) -> str | None:
    return value if value is not None and _SAFE.fullmatch(value) else None
