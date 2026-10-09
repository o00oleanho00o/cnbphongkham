# ported from: src/config/secret-cipher-core.ts
"""Encrypts secrets stored in a database (LLM API keys, bot tokens, credentials) with a key passed by the
caller: AES-256-GCM, format ``base64(iv | authTag | ciphertext)`` with a 12-byte iv and a 16-byte tag.

The SAME wire format as the Node original (``cryptography``'s AESGCM returns ``ciphertext | tag``; it is
re-ordered here), so secrets written by zalo-agent, the clinic app and the agent service read each other's.
One package for every caller: two copies of the same crypto are the easiest place to drift.

Pure module: only ``cryptography``; it never reads settings.
"""

from __future__ import annotations

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

__all__ = ["IV_BYTES", "TAG_BYTES", "decrypt_with", "encrypt_with", "mask_secret"]

IV_BYTES = 12
TAG_BYTES = 16


def _key(key_hex: str) -> bytes:
    key = bytes.fromhex(key_hex)
    if len(key) != 32:
        raise ValueError("encryption key must be 32 bytes (64 hex characters) for AES-256-GCM")
    return key


def encrypt_with(key_hex: str, plaintext: str) -> str:
    iv = os.urandom(IV_BYTES)
    sealed = AESGCM(_key(key_hex)).encrypt(iv, plaintext.encode("utf-8"), None)
    ciphertext, tag = sealed[:-TAG_BYTES], sealed[-TAG_BYTES:]
    return base64.b64encode(iv + tag + ciphertext).decode("ascii")


def decrypt_with(key_hex: str, payload: str) -> str:
    """Raises ``cryptography.exceptions.InvalidTag`` for a wrong key or a tampered payload."""
    raw = base64.b64decode(payload)
    iv, tag, ciphertext = raw[:IV_BYTES], raw[IV_BYTES : IV_BYTES + TAG_BYTES], raw[IV_BYTES + TAG_BYTES :]
    return AESGCM(_key(key_hex)).decrypt(iv, ciphertext + tag, None).decode("utf-8")


def mask_secret(value: str) -> str:
    """``sk-ab...wxyz``: enough to tell WHICH key it is, not enough to reuse it."""
    if not value:
        return "chưa cấu hình"
    if len(value) <= 8:
        return "***"
    return f"{value[:5]}...{value[-4:]}"
