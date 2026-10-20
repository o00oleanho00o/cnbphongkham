"""What the tests of crm-signer share: a fake CRM that records what reaches it, and token helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import httpx
import jwt

from crm_signer import keys

UPSTREAM = "http://api:8000/api/v1/agent-gateway"


@dataclass
class FakeCrm:
    """Answers every call with 200 and the request it saw; ``status`` and ``fail`` change that."""

    calls: list[httpx.Request] = field(default_factory=list[httpx.Request])
    status: int = 200
    fail: Exception | None = None

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        if self.fail is not None:
            raise self.fail
        return httpx.Response(
            self.status,
            json={"url": str(request.url), "body": request.content.decode() or None},
            headers={"retry-after": "7", "x-secret": "no"},
        )


def claims_of(request: httpx.Request, key: keys.SigningKey) -> dict[str, Any]:
    token = request.headers["authorization"].removeprefix("Bearer ")
    return jwt.decode(
        token,
        key.private.public_key(),
        algorithms=["EdDSA"],
        audience="pema-agent-gateway",
        issuer="pema-crm-signer",
    )


def body_of(content: bytes) -> dict[str, Any]:
    return json.loads(content)
