# ported from: src/zalo/zalo-credential-store.ts
"""Cookie Zalo = full quyền tài khoản, nên mã hóa khi lưu (AES-256-GCM).

The original wrote ``data/accounts/<id>/credentials.enc`` ([iv 12][authTag 16][ciphertext]). Here the
credential
(``{"cookie": [...], "imei": "...", "userAgent": "..."}``) lives in ``agent.accounts.credential_enc`` and the
cipher is ``pema.config.secret_cipher`` (the same AES-256-GCM, ``base64(iv | authTag | ciphertext)``).

The vault encrypts BEFORE handing the string to ``AccountStore.set_credential`` and decrypts after
``get_credential``. ``AccountStore`` (package D2) may itself encrypt the column; that is harmless (the
two layers
are symmetric, ``get`` undoes exactly what ``set`` did), and it guarantees the credential is NEVER stored
in clear
even if a store implementation forgets to. A missing ``PEMA_SECRET_ENCRYPTION_KEY`` raises
``SecretKeyMissingError`` and nothing is stored (fail closed).

The credential is never written to a file, never logged and never returned by the API
(``has_credentials`` only).
It goes to the bridge in the body of the signed ``start`` request, and the bridge keeps it in memory.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from uuid import UUID

from pema.config.secret_cipher import decrypt_secret, encrypt_secret
from pema_contracts.agents import AccountStore
from pema_contracts.common import JsonObject


class CredentialVault:
    def __init__(
        self,
        accounts: AccountStore,
        *,
        encrypt: Callable[[str], str] = encrypt_secret,
        decrypt: Callable[[str], str] = decrypt_secret,
    ) -> None:
        self._accounts = accounts
        self._encrypt = encrypt
        self._decrypt = decrypt

    async def has_credentials(self, clinic_id: UUID, account_id: str) -> bool:
        return bool(await self._accounts.get_credential(clinic_id, account_id))

    async def save_credentials(self, clinic_id: UUID, account_id: str, credential: JsonObject) -> None:
        payload = self._encrypt(json.dumps(credential, ensure_ascii=False, separators=(",", ":")))
        await self._accounts.set_credential(clinic_id, account_id, payload)

    async def load_credentials(self, clinic_id: UUID, account_id: str) -> JsonObject | None:
        stored = await self._accounts.get_credential(clinic_id, account_id)
        if not stored:
            return None
        decoded = json.loads(self._decrypt(stored))
        return decoded if isinstance(decoded, dict) else None  # pyright: ignore[reportUnknownVariableType]

    async def delete_credentials(self, clinic_id: UUID, account_id: str) -> None:
        """Account deleted or logged out for good: do not keep the key to the Zalo account."""
        await self._accounts.set_credential(clinic_id, account_id, None)
