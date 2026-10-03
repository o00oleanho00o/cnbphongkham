"""Signed upload paths and file signatures for clinical photos (package U, step U3). New module.

``docs/ARCH-PB01.md``: "POST /media/upload-intent: signed URL, size/malware check". The intent answers with a
path that carries an expiry and an HMAC over (media id, expiry, declared size, MIME type); the upload route
recomputes it from the stored row, so a path cannot be reused for another photo, another size or after the
expiry. The key is a secret of the installation (the one that signs dashboard sessions).

``matches_signature`` is the "malware check" this system can honestly do without looking at pixels: the first
bytes of the file must be the signature of the declared type (JPEG, PNG or WebP). It does not decode the image
and says nothing about its content.
"""

from __future__ import annotations

import hashlib
import hmac
from datetime import datetime
from typing import Final

UPLOAD_TTL_SECONDS: Final = 10 * 60
"""How long an upload path stays valid."""

_JPEG: Final = b"\xff\xd8\xff"
_PNG: Final = b"\x89PNG\r\n\x1a\n"
_PURPOSE: Final = b"pema.media.upload.v1"


def _message(media_id: str, expires: int, size_bytes: int, mime: str) -> bytes:
    return f"{media_id}|{expires}|{size_bytes}|{mime}".encode()


def _key(secret: bytes) -> bytes:
    return hmac.new(secret, _PURPOSE, hashlib.sha256).digest()


def expiry_for(now: datetime) -> int:
    """Unix seconds at which a path issued ``now`` stops working."""
    return int(now.timestamp()) + UPLOAD_TTL_SECONDS


def sign_upload(secret: bytes, media_id: str, expires: int, size_bytes: int, mime: str) -> str:
    return hmac.new(_key(secret), _message(media_id, expires, size_bytes, mime), hashlib.sha256).hexdigest()


def verify_upload(
    secret: bytes, media_id: str, expires: int, size_bytes: int, mime: str, signature: str, now: datetime
) -> bool:
    """``True`` when the signature is genuine for exactly these values and the expiry has not passed."""
    expected = sign_upload(secret, media_id, expires, size_bytes, mime)
    return hmac.compare_digest(expected, signature) and int(now.timestamp()) <= expires


def matches_signature(mime: str, head: bytes) -> bool:
    """The first bytes of a file are those of ``mime`` (``image/jpeg``, ``image/png`` or ``image/webp``)."""
    if mime == "image/jpeg":
        return head.startswith(_JPEG)
    if mime == "image/png":
        return head.startswith(_PNG)
    if mime == "image/webp":
        return len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WEBP"
    return False
