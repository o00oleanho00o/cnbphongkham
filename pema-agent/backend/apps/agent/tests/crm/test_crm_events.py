"""The CRM's events reach the agent (docs/PLAN-crm-plugin.md 3.4, 4): only a fresh token of the CRM with the
events audience is taken, an SSO token never is (and an event token never opens a session), and what is kept is
STATE: the highest version of a visit, the newest consent, the time a visit was last set."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI
from jwt.algorithms import OKPAlgorithm

from agent_app.plugins import PluginHost, discover
from agent_app.runtime import BUNDLED_PLUGINS
from plugins.crm.events import AUDIENCE, ISSUER, EventVerifier, events_router
from plugins.crm.store import MemoryReminderStore, Visit
from plugins.sso import Settings, authenticator
from plugins.sso.keys import KeySet

JWKS = "http://api:8000/api/v1/.well-known/jwks.json"
VISIT = uuid4()
T0 = datetime(2026, 10, 21, 2, 0, tzinfo=UTC)


class Crm:
    """The CRM: signs events (and SSO tokens) with one key and serves its public key; can go down."""

    def __init__(self) -> None:
        self.private = Ed25519PrivateKey.generate()
        self.kid = "crm-1"
        self.down = False

    def _handle(self, request: httpx.Request) -> httpx.Response:
        if self.down:
            return httpx.Response(503)
        jwk = json.loads(OKPAlgorithm.to_jwk(self.private.public_key()))
        return httpx.Response(200, json={"keys": [{**jwk, "kid": self.kid, "use": "sig", "alg": "EdDSA"}]})

    def keys(self) -> KeySet:
        return KeySet(JWKS, transport=httpx.MockTransport(self._handle))

    def token(self, event: dict[str, Any] | None = None, *, ttl: int = 120, **changes: Any) -> str:
        now = int(datetime.now(UTC).timestamp())
        claims: dict[str, Any] = {
            "iss": ISSUER,
            "aud": AUDIENCE,
            "iat": now,
            "exp": now + ttl,
            "jti": str(uuid4()),
            "event": event if event is not None else visit(),
            **changes,
        }
        return jwt.encode(
            {k: v for k, v in claims.items() if v is not None},
            self.private,
            algorithm="EdDSA",
            headers={"kid": self.kid},
        )


def visit(**over: Any) -> dict[str, Any]:
    event = {
        "kind": "appointment.changed",
        "appointment_id": str(VISIT),
        "channel": "zalo-acc1",
        "external_id": "u123",
        "starts_at": "2026-10-22T09:30:00+07:00",
        "duration_min": 30,
        "status": "booked",
        "version": 1,
        "messages_consent": True,
        "actor_type": "agent",
        "occurred_at": T0.isoformat(),
    }
    return event | over


@pytest.fixture
def crm() -> Crm:
    return Crm()


@pytest.fixture
def store() -> MemoryReminderStore:
    return MemoryReminderStore()


@pytest.fixture
def client(crm: Crm, store: MemoryReminderStore) -> httpx.AsyncClient:
    app = FastAPI()
    app.include_router(events_router(EventVerifier(crm.keys()), store))
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://agent")


async def _send(client: httpx.AsyncClient, token: str | None) -> httpx.Response:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return await client.post("/events", headers=headers)


async def test_an_event_of_the_crm_is_kept(
    client: httpx.AsyncClient, crm: Crm, store: MemoryReminderStore
) -> None:
    answer = await _send(client, crm.token())

    assert answer.status_code == 200
    assert answer.json() == {"ok": True, "code": "applied"}
    kept = await store.visit(VISIT)
    assert kept is not None
    assert (kept.status, kept.version, kept.channel, kept.external_id) == ("booked", 1, "zalo-acc1", "u123")
    person = await store.person("zalo-acc1", "u123")
    assert person is not None
    assert person.messages_consent is True


@pytest.mark.parametrize(
    "changes",
    [
        {"aud": "pema-agent"},  # an SSO token of the clinic is not an event
        {"iss": "pema-crm-signer"},
        {"ttl": 600},  # longer than the CRM ever signs
        {"ttl": -120},  # expired
        {"jti": None},
    ],
)
async def test_anything_but_a_fresh_event_token_is_401_and_nothing_is_kept(
    client: httpx.AsyncClient, crm: Crm, store: MemoryReminderStore, changes: dict[str, Any]
) -> None:
    answer = await _send(client, crm.token(**changes))

    assert answer.status_code == 401
    assert await store.visit(VISIT) is None


async def test_no_token_a_forged_one_or_an_unknown_key_is_401(
    client: httpx.AsyncClient, crm: Crm, store: MemoryReminderStore
) -> None:
    forger = Crm()  # same kid, another private key
    other_kid = Crm()
    other_kid.kid = "nobody"

    assert (await _send(client, None)).status_code == 401
    assert (await _send(client, "not.a.jwt")).status_code == 401
    assert (await _send(client, forger.token())).status_code == 401
    assert (await _send(client, other_kid.token())).status_code == 401
    assert await store.visit(VISIT) is None


async def test_the_crm_keys_down_is_503_so_the_crm_tries_again(client: httpx.AsyncClient, crm: Crm) -> None:
    crm.down = True
    assert (await _send(client, crm.token())).status_code == 503


async def test_a_broken_event_is_422_and_an_unknown_kind_is_taken_and_ignored(
    client: httpx.AsyncClient, crm: Crm
) -> None:
    broken = await _send(client, crm.token(visit(version="two")))
    unknown = await _send(client, crm.token({"kind": "invoice.paid"}))

    assert broken.status_code == 422
    assert unknown.status_code == 200
    assert unknown.json()["code"] == "ignored"


async def test_state_older_or_repeated_events_change_nothing(
    client: httpx.AsyncClient, crm: Crm, store: MemoryReminderStore
) -> None:
    await _send(client, crm.token(visit(version=3, status="confirmed")))
    await _send(client, crm.token(visit(version=2, status="cancelled")))  # late
    await _send(client, crm.token(visit(version=3, status="cancelled")))  # same version again

    kept = await store.visit(VISIT)
    assert kept is not None
    assert (kept.version, kept.status) == (3, "confirmed")


async def test_changed_at_moves_with_the_time_not_with_the_status(
    client: httpx.AsyncClient, crm: Crm, store: MemoryReminderStore
) -> None:
    later = T0 + timedelta(hours=1)
    much_later = T0 + timedelta(hours=2)
    await _send(client, crm.token(visit(version=1)))
    await _send(client, crm.token(visit(version=2, status="confirmed", occurred_at=later.isoformat())))
    confirmed = await store.visit(VISIT)
    moved_to = "2026-10-22T14:00:00+07:00"
    await _send(client, crm.token(visit(version=3, starts_at=moved_to, occurred_at=much_later.isoformat())))
    moved = await store.visit(VISIT)

    assert confirmed is not None
    assert confirmed.changed_at == T0  # confirming does not reset the clock of the reminder marks
    assert moved is not None
    assert moved.changed_at == much_later
    assert moved.starts_at == datetime.fromisoformat(moved_to)


async def test_the_newest_consent_wins_whichever_event_carries_it(
    client: httpx.AsyncClient, crm: Crm, store: MemoryReminderStore
) -> None:
    refused_at = T0 + timedelta(minutes=5)
    person_event = {
        "kind": "person.changed",
        "channel": "zalo-acc1",
        "external_id": "u123",
        "messages_consent": False,
        "actor_type": "user",
        "occurred_at": refused_at.isoformat(),
    }
    await _send(client, crm.token(person_event))
    await _send(client, crm.token(visit(version=1)))  # older, says True

    person = await store.person("zalo-acc1", "u123")
    assert person is not None
    assert person.messages_consent is False
    assert person.consent_at == refused_at


async def test_the_sso_plugin_never_takes_an_event_token_as_a_session(crm: Crm) -> None:
    settings = Settings(issuer=ISSUER, audience="pema-agent", jwks_url=JWKS)
    authenticate = authenticator(settings, crm.keys())

    assert await authenticate(crm.token(sub="user-1", scope="admin")) is None


async def test_the_plugin_mounts_the_events_route_among_its_hooks(crm: Crm) -> None:
    host = PluginHost(discover([("bundled", BUNDLED_PLUGINS)]).plugins, {})
    host.enable("crm", {"keys_transport": httpx.MockTransport(crm._handle)})  # pyright: ignore[reportPrivateUsage]
    hooks = host.routes("crm", "hooks")
    assert hooks is not None

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=hooks), base_url="http://agent") as c:
        answer = await c.post("/events", headers={"Authorization": f"Bearer {crm.token()}"})

    assert answer.status_code == 200


async def test_an_applied_event_hands_on_the_visit_as_it_was_and_an_ignored_one_nothing(crm: Crm) -> None:
    woken: list[Visit | None] = []

    async def changed(before: Visit | None) -> None:
        woken.append(before)

    app = FastAPI()
    app.include_router(events_router(EventVerifier(crm.keys()), MemoryReminderStore(), changed))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://agent") as c:
        await _send(c, crm.token({"kind": "invoice.paid"}))
        await _send(c, crm.token())
        await _send(c, crm.token(visit(version=2, starts_at="2026-10-23T09:30:00+07:00")))

    assert woken[0] is None  # a visit not known before
    assert len(woken) == 2
    assert woken[1] is not None
    assert woken[1].starts_at == datetime(2026, 10, 22, 2, 30, tzinfo=UTC)  # the time it had
