"""Seals the secrets kept in the store (bot tokens, personal-account credentials, OA keys) with Fernet.

New module; it replaces the agent's ``ctx.encrypt`` (secretcipher), which this service does not import.
``ZALO_SECRET_KEY`` may be any string: the Fernet key is the sha256 of it.
"""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken


class Seal:
    def __init__(self, secret_key: str) -> None:
        if not secret_key:
            raise ValueError("ZALO_SECRET_KEY is empty")
        self._fernet = Fernet(base64.urlsafe_b64encode(hashlib.sha256(secret_key.encode("utf-8")).digest()))

    def encrypt(self, text: str) -> str:
        return self._fernet.encrypt(text.encode("utf-8")).decode("ascii")

    def decrypt(self, sealed: str) -> str:
        """``ValueError`` when the text was not sealed with this key."""
        try:
            return self._fernet.decrypt(sealed.encode("ascii")).decode("utf-8")
        except (InvalidToken, UnicodeError) as err:
            raise ValueError("the sealed text does not open with this key") from err
