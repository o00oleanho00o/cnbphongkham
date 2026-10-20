"""What the tests of the agent gateway share (docs/PLAN-crm-plugin.md): the signer's key, the tokens it
makes, a client that signs every call, and a few helpers.

Test support like ``clinic_testing``: production code never imports it. The fixtures are in
``tests/clinic/conftest.py``.
"""

from __future__ import annotations

import base64
import itertools
import time
from collections.abc import Awaitable, Callable, Generator
from datetime import date, datetime, timedelta
from typing import Any
from uuid import uuid4

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from sqlalchemy import text
from sqlalchemy.engine import Engine

from pema.api.agent_gateway_auth import AUDIENCE, ISSUER
from pema_contracts.common import VN_TZ
from pema_contracts.roles import Permission

KEY = Ed25519PrivateKey.generate()  # crm-signer's key, made fresh for this test run
OTHER_KEY = Ed25519PrivateKey.generate()
ALL_SCOPES = " ".join(p.value for p in Permission if p.value.startswith("agent."))
GW = "/api/v1/agent-gateway"
DOCTORS = 3  # owner, doctor.mai, doctor.an of the demo seed

_days = itertools.count(1)


def free_day() -> date:
    """A new day of 2027 per call: no test sees another test's visits."""
    return date(2027, 3, 1) + timedelta(days=next(_days))


def at(day: date, hour: int, minute: int = 0) -> str:
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=VN_TZ).isoformat()


def person() -> str:
    return f"{GW}/contacts/zalo-test/{uuid4().hex}"


def public(key: Ed25519PrivateKey) -> str:
    raw = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def token(key: Ed25519PrivateKey = KEY, *, scope: str = ALL_SCOPES, **claims: Any) -> str:
    """What crm-signer sends: a fresh JWT per call. A claim given as None is left out."""
    now = int(time.time())
    body: dict[str, Any] = {"iss": ISSUER, "aud": AUDIENCE, "iat": now, "exp": now + 120, "jti": uuid4().hex}
    body["scope"] = scope
    body.update(claims)
    return jwt.encode({k: v for k, v in body.items() if v is not None}, key, algorithm="EdDSA")


class Signer(httpx.Auth):
    def auth_flow(self, request: httpx.Request) -> Generator[httpx.Request, httpx.Response]:
        request.headers["Authorization"] = f"Bearer {token()}"
        yield request


def bearer(value: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {value}"}


Save = Callable[..., Awaitable[str]]


async def book(agent: httpx.AsyncClient, path: str, starts_at: str, key: str | None = None) -> httpx.Response:
    return await agent.post(
        f"{path}/appointments",
        json={"starts_at": starts_at, "duration_min": 30, "note": "Tư vấn da"},
        headers={"Idempotency-Key": key or uuid4().hex},
    )


def rows(admin: Engine, sql: str, **params: Any) -> list[Any]:
    with admin.connect() as conn:
        return list(conn.execute(text(sql), params).all())
