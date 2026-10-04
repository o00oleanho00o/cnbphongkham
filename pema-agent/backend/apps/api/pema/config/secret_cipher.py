# ported from: src/config/secret-cipher.ts
"""Encrypt the secrets stored in the database: LLM API keys, search provider keys, the Zalo bot token, the
personal-account credential, MCP headers. AES-256-GCM with the key of ``Settings.secret_encryption_key``
(``PEMA_SECRET_ENCRYPTION_KEY``, 64 hex chars); format ``base64(iv | authTag | ciphertext)``.

One module for all callers because two copies of the same crypto are the easiest place to drift. This file
only wires the key; the algorithm is in ``secret_cipher_core``.

Deviation: the original read ``env.CREDENTIALS_ENCRYPTION_KEY`` (required at boot). Here a missing key
raises ``SecretKeyMissingError`` when a secret is actually encrypted or decrypted, so tests and processes
that never touch a secret need no key.
"""

from __future__ import annotations

from pema.config.env import get_settings
from pema.config.secret_cipher_core import decrypt_with, encrypt_with, mask_secret

__all__ = ["SecretKeyMissingError", "decrypt_secret", "encrypt_secret", "mask_secret"]


class SecretKeyMissingError(RuntimeError):
    """``PEMA_SECRET_ENCRYPTION_KEY`` is not configured."""


def _key() -> str:
    secret = get_settings().secret_encryption_key
    if secret is None:
        raise SecretKeyMissingError("PEMA_SECRET_ENCRYPTION_KEY is not set")
    return secret.get_secret_value()


def encrypt_secret(plaintext: str) -> str:
    return encrypt_with(_key(), plaintext)


def decrypt_secret(payload: str) -> str:
    return decrypt_with(_key(), payload)
