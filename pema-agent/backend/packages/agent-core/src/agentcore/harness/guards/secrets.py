"""Masks secrets in text the model is about to read: well-known credential shapes and the exact values of
secret-looking environment variables (``*KEY``, ``*TOKEN``, ``*SECRET``, ``*PASSWORD``)."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Final

REDACTED: Final = "[redacted]"
MIN_SECRET_VALUE_CHARS: Final = 8

_SECRET_NAME: Final = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD)S?$", re.IGNORECASE)
_SHAPES: Final = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.DOTALL),
    re.compile(r"\bsk-ant-[A-Za-z0-9_-]{16,}"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}"),
    re.compile(r"\bxox[abpr]-[A-Za-z0-9-]{10,}"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
)
_BEARER: Final = re.compile(r"(?i)(\bbearer\s+)[A-Za-z0-9._~+/=-]{16,}")


class SecretRedactor:
    def __init__(self, env: Mapping[str, str]) -> None:
        values = {
            value
            for name, value in env.items()
            if _SECRET_NAME.search(name) and len(value) >= MIN_SECRET_VALUE_CHARS
        }
        # Longest first, so a secret that contains another is masked whole.
        self._values = sorted(values, key=len, reverse=True)

    def redact(self, text: str) -> str:
        for value in self._values:
            text = text.replace(value, REDACTED)
        for shape in _SHAPES:
            text = shape.sub(REDACTED, text)
        return _BEARER.sub(rf"\1{REDACTED}", text)
