"""The Ed25519 private key of ``crm-signer``: a file only this service mounts (docs/PLAN-crm-plugin.md 3.9).

``generate`` makes it once (``crm-signer keygen``) and never replaces a file; ``load`` never makes one, so a
service without its key does not start. The public half is printed for ``PEMA_AGENT_GATEWAY_PUBLIC_KEYS``.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


@dataclass(frozen=True)
class SigningKey:
    private: Ed25519PrivateKey
    kid: str
    x: str
    """The raw public key, base64url: what the CRM is given."""


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def signing_key(private: Ed25519PrivateKey) -> SigningKey:
    raw = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    x = _b64url(raw)
    thumbprint = json.dumps({"crv": "Ed25519", "kty": "OKP", "x": x}, separators=(",", ":"))  # RFC 7638
    return SigningKey(private=private, kid=_b64url(hashlib.sha256(thumbprint.encode()).digest()), x=x)


def generate(path: Path) -> SigningKey:
    """Write a new key at ``path`` (mode 0600). A key in use is never replaced:
    an existing file is refused."""
    private = Ed25519PrivateKey.generate()
    pem = private.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as out:
        out.write(pem)
    return signing_key(private)


def load(path: Path) -> SigningKey:
    loaded = serialization.load_pem_private_key(path.read_bytes(), password=None)
    if not isinstance(loaded, Ed25519PrivateKey):
        raise ValueError(f"{path} does not hold an Ed25519 private key")
    return signing_key(loaded)
