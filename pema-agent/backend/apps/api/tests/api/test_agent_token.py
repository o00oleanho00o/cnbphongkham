"""Agent tokens (plan C, step C1): the clinic signs a short EdDSA token for a signed-in admin; the agent checks it
with the public key set, which is open. Unit tests need nothing; the HTTP ones need ``PEMA_TEST_DATABASE_URL``."""

from __future__ import annotations

import os
import stat
from collections.abc import Iterator
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import jwt
import pytest
from fastapi import FastAPI

from pema.api import agent_token
from pema.api.clinic_testing import DEMO_NOW, ClientFactory
from pema.api.dashboard_auth import AuthenticatedUser
from pema.clinic.actions.seed_demo import SeedResult
from pema.config.env import get_settings
from pema_contracts.roles import Role


def _user(**changes: Any) -> AuthenticatedUser:
    user = AuthenticatedUser(
        user_id=uuid4(),
        clinic_id=uuid4(),
        role=Role.MANAGER,
        display_name="Quản lý Hạnh (mẫu)",
        clinic_name="Phòng khám mẫu",
        session_id=uuid4(),
        expires_at=DEMO_NOW + timedelta(hours=8),
        absolute_expires_at=DEMO_NOW + timedelta(days=7),
    )
    return replace(user, **changes)


def _verify(token: str, jwks: dict[str, Any]) -> dict[str, Any]:
    """What the agent does: pick the key by ``kid`` from the open key set, check signature, audience, issuer."""
    kid = jwt.get_unverified_header(token)["kid"]
    key = next((k for k in jwt.PyJWKSet.from_dict(jwks).keys if k.key_id == kid), None)
    if key is None:
        raise LookupError(kid)
    return jwt.decode(
        token,
        key.key,
        algorithms=["EdDSA"],
        audience=agent_token.AUDIENCE,
        issuer=agent_token.ISSUER,
        options={"verify_exp": False},  # the demo clock is frozen in the past
    )


def test_the_key_is_made_once_and_read_back(tmp_path: Path) -> None:
    first = agent_token.load_or_create_key(tmp_path)
    second = agent_token.load_or_create_key(tmp_path)

    assert first.kid == second.kid
    assert [p.name for p in tmp_path.iterdir()] == [agent_token.KEY_FILE]
    if os.name == "posix":
        assert stat.S_IMODE((tmp_path / agent_token.KEY_FILE).stat().st_mode) == 0o600


def test_a_file_that_holds_another_kind_of_key_is_refused(tmp_path: Path) -> None:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    pem = ec.generate_private_key(ec.SECP256R1()).private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    (tmp_path / agent_token.KEY_FILE).write_bytes(pem)

    with pytest.raises(ValueError, match="Ed25519"):
        agent_token.load_or_create_key(tmp_path)


def test_a_token_names_the_user_lives_two_minutes_and_checks_with_the_public_key(tmp_path: Path) -> None:
    key = agent_token.load_or_create_key(tmp_path)
    user = _user()

    token, expires_at = agent_token.mint(key, user, DEMO_NOW)
    claims = _verify(token, {"keys": [key.public_jwk()]})

    assert jwt.get_unverified_header(token)["alg"] == "EdDSA"
    assert (claims["sub"], claims["name"], claims["role"], claims["scope"]) == (
        str(user.user_id),
        user.display_name,
        "manager",
        "admin",
    )
    assert expires_at == DEMO_NOW + agent_token.TOKEN_TTL
    assert claims["exp"] == claims["iat"] + 120
    assert "d" not in key.public_jwk()


def test_a_token_never_outlives_its_session(tmp_path: Path) -> None:
    key = agent_token.load_or_create_key(tmp_path)
    ending = DEMO_NOW + timedelta(seconds=30)

    _, expires_at = agent_token.mint(key, _user(expires_at=ending), DEMO_NOW)

    assert expires_at == ending


def test_a_token_signed_with_another_key_or_for_another_audience_is_refused(tmp_path: Path) -> None:
    ours = agent_token.load_or_create_key(tmp_path / "ours")
    theirs = agent_token.load_or_create_key(tmp_path / "theirs")
    forged, _ = agent_token.mint(theirs, _user(), DEMO_NOW)
    elsewhere = jwt.encode(
        {"iss": agent_token.ISSUER, "aud": "someone-else", "sub": "x", "exp": 9_999_999_999},
        ours.private,
        algorithm="EdDSA",
        headers={"kid": ours.kid},
    )

    with pytest.raises(LookupError):  # unknown kid: the agent fetches the set again, then refuses
        _verify(forged, {"keys": [ours.public_jwk()]})
    with pytest.raises(jwt.InvalidAudienceError):
        _verify(elsewhere, {"keys": [ours.public_jwk()]})


# ---------------------------------------------------------------- through the HTTP API (real Postgres)


@pytest.fixture
def key_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    monkeypatch.setenv("PEMA_DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    yield tmp_path
    get_settings.cache_clear()


@pytest.mark.db
async def test_an_admin_gets_a_token_others_are_refused_and_the_key_set_is_open(
    app: FastAPI, world: SeedResult, client_factory: ClientFactory, key_dir: Path
) -> None:
    owner = await client_factory("owner")
    manager = await client_factory("manager")
    reception = await client_factory("reception.lan")
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as anonymous:
        nobody = await anonymous.post("/api/v1/auth/agent-token")
        jwks = await anonymous.get("/api/v1/.well-known/jwks.json")

    for_owner = await owner.post("/api/v1/auth/agent-token")
    for_manager = await manager.post("/api/v1/auth/agent-token")
    refused = await reception.post("/api/v1/auth/agent-token")

    assert (nobody.status_code, refused.status_code) == (401, 403)
    assert refused.json()["error"]["code"] == "forbidden"
    assert (for_owner.status_code, for_manager.status_code, jwks.status_code) == (200, 200, 200)
    assert for_owner.headers["cache-control"] == "no-store"
    assert jwks.headers["cache-control"] == "public, max-age=300"
    claims = _verify(for_manager.json()["token"], jwks.json())
    assert (claims["role"], claims["scope"]) == ("manager", "admin")
    assert (key_dir / agent_token.KEY_FILE).is_file()
