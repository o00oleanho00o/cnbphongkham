# ported from: src/config/secret-cipher-core.ts
"""The PURE cryptographic part of ``secret_cipher``: it takes the key as an argument instead of reading
settings.

Split out because some callers must decrypt WITHOUT loading settings (the eval harness reads the LLM
config from the real DB before it builds a temporary environment). The algorithm itself lives in the shared
workspace package ``secretcipher`` (AES-256-GCM, ``base64(iv | authTag | ciphertext)``, the Node wire
format), which the agent service uses too; this module keeps the clinic's import path.
"""

from __future__ import annotations

from secretcipher import IV_BYTES, TAG_BYTES, decrypt_with, encrypt_with, mask_secret

__all__ = ["IV_BYTES", "TAG_BYTES", "decrypt_with", "encrypt_with", "mask_secret"]
