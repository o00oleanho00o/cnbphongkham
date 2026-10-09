"""The ``sso`` plugin: a short token signed by the issuer's private key opens the routes its scope names, checked
with the public keys the issuer publishes; anything else is left to the other sign-ins or refused; the keys
are fetched rarely and an unreachable issuer gives 503, not 401. The clinic profile loads with it."""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from jwt.algorithms import OKPAlgorithm

from agent_app.auth import ADMIN, CHAT, Principal
from agent_app.gateway import GatewaySettings, create_app
from agent_app.profile import load_profile
from agent_app.runtime import build_runtime
from plugins.sso import Settings, authenticator, scopes_of
from plugins.sso.keys import KeySet, KeysUnavailableError

CLINIC_PROFILE = Path(__file__).resolve().parents[2] / "agents" / "clinic"
ISSUER = "pema-clinic"
AUDIENCE = "pema-agent"
JWKS_URL = "http://api:8000/api/v1/.well-known/jwks.json"
SETTINGS = Settings(issuer=ISSUER, audience=AUDIENCE, jwks_url=JWKS_URL)
KEY = "0f" * 32


class Issuer:
    """The other service: signs tokens and serves its public keys; can rotate its key or go down."""

    def __init__(self) -> None:
        self.calls = 0
        self.down = False
        self.rotate()

    def rotate(self) -> None:
        self.private = Ed25519PrivateKey.generate()
        self.kid = f"k{self.calls}-{id(self.private)}"

    def jwks(self) -> dict[str, Any]:
        jwk = json.loads(OKPAlgorithm.to_jwk(self.private.public_key()))
        return {"keys": [{**jwk, "kid": self.kid, "use": "sig", "alg": "EdDSA"}]}

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        if self.down:
            return httpx.Response(503)
        assert str(request.url) == JWKS_URL
        return httpx.Response(200, json=self.jwks())

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def token(self, scope: str = "admin", *, kid: str | None = None, **changes: Any) -> str:
        now = datetime.now(UTC)
        claims: dict[str, Any] = {
            "iss": ISSUER,
            "aud": AUDIENCE,
            "sub": "user-1",
            "scope": scope,
            "iat": now,
            "exp": now + timedelta(minutes=2),
            **changes,
        }
        return jwt.encode(claims, self.private, algorithm="EdDSA", headers={"kid": kid or self.kid})


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def issuer() -> Issuer:
    return Issuer()


def test_settings_need_all_three_values_and_an_http_url() -> None:
    with pytest.raises(ValueError, match="audience, jwks_url"):
        Settings.of({"issuer": ISSUER, "audience": " "})
    with pytest.raises(ValueError, match="http"):
        Settings.of({"issuer": ISSUER, "audience": AUDIENCE, "jwks_url": "file:///etc/passwd"})
    assert Settings.of({"issuer": ISSUER, "audience": AUDIENCE, "jwks_url": JWKS_URL}) == SETTINGS


def test_admin_includes_chat_and_unknown_scopes_give_nothing() -> None:
    assert scopes_of("admin") == {ADMIN, CHAT}
    assert scopes_of("read chat") == {CHAT}
    assert scopes_of("owner") == frozenset()


async def test_a_valid_token_is_a_caller_with_its_scopes(issuer: Issuer) -> None:
    authenticate = authenticator(SETTINGS, KeySet(JWKS_URL, transport=issuer.transport()))

    admin = await authenticate(issuer.token("admin"))
    chat = await authenticate(issuer.token("chat"))
    none = await authenticate(issuer.token("", sub="user-2"))

    assert admin == Principal("sso:user-1", frozenset({ADMIN, CHAT}))
    assert chat == Principal("sso:user-1", frozenset({CHAT}))
    assert none == Principal("sso:user-2", frozenset())
    assert issuer.calls == 1


async def test_tokens_of_others_are_left_alone_without_fetching_keys(issuer: Issuer) -> None:
    authenticate = authenticator(SETTINGS, KeySet(JWKS_URL, transport=issuer.transport()))
    shared_secret = jwt.encode({"iss": ISSUER, "sub": "x", "aud": AUDIENCE}, "s" * 32, algorithm="HS256")

    found = [
        await authenticate("pak_not-a-jwt"),
        await authenticate("a.b.c"),
        await authenticate(issuer.token(iss="someone-else")),
        await authenticate(shared_secret),
    ]

    assert found == [None, None, None, None]
    assert issuer.calls == 0


async def test_wrong_audience_expired_unsigned_or_forged_tokens_are_refused(issuer: Issuer) -> None:
    authenticate = authenticator(SETTINGS, KeySet(JWKS_URL, transport=issuer.transport()))
    long_ago = datetime.now(UTC) - timedelta(hours=1)
    forger = Ed25519PrivateKey.generate()
    forged = jwt.encode(
        {"iss": ISSUER, "aud": AUDIENCE, "sub": "x", "iat": long_ago, "exp": long_ago + timedelta(days=9)},
        forger,
        algorithm="EdDSA",
        headers={"kid": issuer.kid},
    )

    found = [
        await authenticate(issuer.token(aud="another-agent")),
        await authenticate(issuer.token(iat=long_ago, exp=long_ago + timedelta(minutes=2))),
        await authenticate(issuer.token(sub="")),
        await authenticate(forged),
    ]

    assert found == [None, None, None, None]


async def test_keys_are_fetched_again_on_a_new_kid_but_not_more_than_every_retry_window(
    issuer: Issuer,
) -> None:
    clock = Clock()
    authenticate = authenticator(SETTINGS, KeySet(JWKS_URL, clock=clock, transport=issuer.transport()))
    assert await authenticate(issuer.token()) is not None
    issuer.rotate()
    rotated = issuer.token()

    too_soon = await authenticate(rotated)
    made_up = [await authenticate(issuer.token(kid=f"x{i}")) for i in range(5)]
    clock.now += 31
    later = await authenticate(rotated)

    assert too_soon is None
    assert made_up == [None] * 5
    assert later is not None
    assert issuer.calls == 2


async def test_while_the_issuer_is_down_known_keys_work_and_unknown_ones_cannot_be_checked(
    issuer: Issuer,
) -> None:
    clock = Clock()
    keys = KeySet(JWKS_URL, max_age_s=60, clock=clock, transport=issuer.transport())
    authenticate = authenticator(SETTINGS, keys)
    known = issuer.token()
    assert await authenticate(known) is not None
    issuer.down = True
    clock.now += 61

    still = await authenticate(known)
    issuer.rotate()
    with pytest.raises(KeysUnavailableError):
        await authenticate(issuer.token())

    assert still is not None
    assert issuer.calls == 2


# ---------------------------------------------------------------- the clinic profile through the gateway


@pytest.fixture
def service(tmp_path: Path, issuer: Issuer, monkeypatch: pytest.MonkeyPatch) -> Iterator[httpx.AsyncClient]:
    env = {"AGENT_SECRET_ENCRYPTION_KEY": KEY, "AGENT_DATA_DIR": str(tmp_path / "home")}
    runtime = build_runtime(load_profile(CLINIC_PROFILE), fake=True, env=env, db=None)
    app = create_app(runtime.dispatcher(), GatewaySettings(), plugins=runtime.plugin_manager)
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://agent")
    real = httpx.AsyncClient

    def to_issuer(*, timeout: float, transport: object = None) -> httpx.AsyncClient:
        return real(timeout=timeout, transport=issuer.transport())

    monkeypatch.setattr(httpx, "AsyncClient", to_issuer)
    yield client
    runtime.close()


async def test_the_clinic_profile_lets_the_issuers_admins_in(
    service: httpx.AsyncClient, issuer: Issuer
) -> None:
    async with service as client:
        admin = await client.get("/v1/admin/plugins", headers=_bearer(issuer.token("admin")))
        chat_only = await client.get("/v1/admin/plugins", headers=_bearer(issuer.token("chat")))
        garbage = await client.get("/v1/admin/plugins", headers=_bearer("a.b.c"))

    assert admin.status_code == 200
    assert '"sso"' in admin.text
    assert (chat_only.status_code, garbage.status_code) == (403, 401)


async def test_an_unreachable_issuer_is_503_not_a_wrong_token(
    service: httpx.AsyncClient, issuer: Issuer
) -> None:
    issuer.down = True
    async with service as client:
        unreachable = await client.get("/v1/admin/plugins", headers=_bearer(issuer.token("admin")))

    assert unreachable.status_code == 503


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
