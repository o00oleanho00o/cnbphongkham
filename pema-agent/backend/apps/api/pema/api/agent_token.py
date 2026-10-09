"""Short tokens with which the clinic web calls the agent service for a signed-in staff member, and the public
key that checks them (plan C, docs/HANDOFF-agent-v2.md).

The web's server asks for one with the staff member's cookie (``POST /auth/agent-token``) and sends it to the
agent as ``Authorization: Bearer``: the browser never needs it and the agent never sees the cookie. The agent
reads the public key (``GET /.well-known/jwks.json``), so the two services share no secret. The Ed25519
private key is made on first use in ``PEMA_DATA_DIR`` and never leaves this process; deleting the file and
restarting rotates it (the agent fetches the keys again when it meets an unknown ``kid``).
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Final
from uuid import uuid4

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from pema.api.dashboard_auth import AuthenticatedUser
from pema.config.env import get_settings

ISSUER: Final = "pema-clinic"
AUDIENCE: Final = "pema-agent"
ALGORITHM: Final = "EdDSA"
TOKEN_TTL: Final = timedelta(minutes=2)
KEY_FILE: Final = "agent-token-ed25519.pem"
ADMIN_SCOPE: Final = "admin"


@dataclass(frozen=True)
class SigningKey:
    private: Ed25519PrivateKey
    kid: str
    x: str
    """The raw public key, base64url."""

    def public_jwk(self) -> dict[str, str]:
        return {"kty": "OKP", "crv": "Ed25519", "x": self.x, "kid": self.kid, "use": "sig", "alg": ALGORITHM}


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _signing_key(private: Ed25519PrivateKey) -> SigningKey:
    raw = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    x = _b64url(raw)
    # RFC 7638 thumbprint: the required members in lexical order, no whitespace.
    thumbprint = json.dumps({"crv": "Ed25519", "kty": "OKP", "x": x}, separators=(",", ":"))
    return SigningKey(private=private, kid=_b64url(hashlib.sha256(thumbprint.encode()).digest()), x=x)


def load_or_create_key(folder: Path) -> SigningKey:
    """The key of ``folder``, made the first time. Written beside the target then linked into place, so a
    second process never reads half a file and never replaces a key the first one already uses."""
    path = folder / KEY_FILE
    if not path.exists():
        folder.mkdir(parents=True, exist_ok=True)
        pem = Ed25519PrivateKey.generate().private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        )
        draft = folder / f".{KEY_FILE}.{uuid4().hex}"
        descriptor = os.open(draft, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as out:
                out.write(pem)
            with contextlib.suppress(FileExistsError):  # another process made it first: use theirs
                os.link(draft, path)
        finally:
            draft.unlink(missing_ok=True)
    loaded = serialization.load_pem_private_key(path.read_bytes(), password=None)
    if not isinstance(loaded, Ed25519PrivateKey):
        raise ValueError(f"{path} does not hold an Ed25519 private key")
    return _signing_key(loaded)


@lru_cache
def _key_of(folder: Path) -> SigningKey:
    return load_or_create_key(folder)


def signing_key() -> SigningKey:
    return _key_of(get_settings().data_dir.resolve())


def mint(key: SigningKey, user: AuthenticatedUser, at: datetime) -> tuple[str, datetime]:
    """A token for ``user``, valid ``TOKEN_TTL`` but never past the end of the session it came from."""
    expires_at = min(at + TOKEN_TTL, user.expires_at)
    claims = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": str(user.user_id),
        "name": user.display_name,
        "role": user.role.value,
        "scope": ADMIN_SCOPE,
        "iat": int(at.timestamp()),
        "exp": int(expires_at.timestamp()),
        "jti": uuid4().hex,
    }
    token = jwt.encode(claims, key.private, algorithm=ALGORITHM, headers={"kid": key.kid})
    return token, expires_at
