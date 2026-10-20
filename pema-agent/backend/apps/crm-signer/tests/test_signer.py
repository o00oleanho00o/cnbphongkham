"""What crm-signer must do (docs/PLAN-crm-plugin.md 3.9, 4)."""

from __future__ import annotations

import logging
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from starlette.testclient import TestClient

from crm_signer import cli, keys
from crm_signer.app import MAX_BODY, PER_MINUTE, TOKEN_TTL_S, create_app
from crm_signer.routes import ROUTES, match
from crm_signer.testing import UPSTREAM, FakeCrm, body_of, claims_of

GW = "/agent-gateway"
PERSON = "/contacts/zalo/u123"
VISIT = f"{PERSON}/appointments/{uuid4()}"


def test_every_route_is_signed_with_its_own_scope(
    client: TestClient, crm: FakeCrm, key: keys.SigningKey
) -> None:
    for route in ROUTES:
        path = route.template.format(channel="zalo", external_id="u123", appointment_id=str(uuid4()))
        body = None if route.method == "GET" else b"{}"
        answer = client.request(route.method, GW + path, content=body)
        assert answer.status_code == 200, (route, answer.text)
        claims = claims_of(crm.calls[-1], key)
        assert claims["scope"] == route.scope
        assert claims["exp"] - claims["iat"] == TOKEN_TTL_S <= 120
        assert len(str(claims["jti"])) >= 32
        assert str(crm.calls[-1].url) == UPSTREAM + path
    assert len({claims_of(c, key)["jti"] for c in crm.calls}) == len(ROUTES), "one token per call"


def test_query_and_body_travel_on(client: TestClient, crm: FakeCrm) -> None:
    client.get(f"{GW}/free-slots?day_from=2026-10-21&days=2")
    assert crm.calls[-1].url.query == b"day_from=2026-10-21&days=2"
    answer = client.post(f"{GW}{PERSON}/appointments", content=b'{"starts_at": "x"}')
    assert body_of(answer.content)["body"] == '{"starts_at": "x"}'


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", f"{GW}{PERSON}"),  # no GET on a contact
        ("DELETE", f"{GW}{PERSON}"),
        ("POST", f"{GW}/free-slots"),
        ("GET", f"{GW}/appointments"),  # the staff route, not the gateway's
        ("GET", f"{GW}/../appointments"),
        ("GET", f"{GW}{PERSON}/appointments/not-a-uuid/confirm"),
        ("POST", f"{GW}{VISIT}/confirm/extra"),
        ("GET", f"{GW}{PERSON}/appointments/"),
        ("GET", f"/api/v1{GW}/free-slots"),
        ("GET", f"{GW}/free-slots?q=" + "a" * 600),
    ],
)
def test_anything_else_is_404_and_never_reaches_the_crm(
    client: TestClient, crm: FakeCrm, method: str, path: str
) -> None:
    answer = client.request(method, path)
    assert answer.status_code == 404
    assert crm.calls == []


def test_dots_never_match_a_person() -> None:
    assert match("GET", "/contacts/./u1/appointments") is None
    assert match("GET", "/contacts/zalo/../appointments") is None
    assert match("GET", "/contacts/zalo/u.1/appointments") is not None


def test_only_the_allowed_headers_travel(client: TestClient, crm: FakeCrm) -> None:
    client.post(
        f"{GW}{PERSON}/appointments",
        content=b"{}",
        headers={
            "Authorization": "Bearer forged",
            "Cookie": "pema_session=abc",
            "Idempotency-Key": "k1",
            "X-Request-Id": "r1",
            "X-Forwarded-For": "1.2.3.4",
        },
    )
    sent = crm.calls[-1].headers
    assert sent["authorization"].startswith("Bearer ")
    assert sent["authorization"] != "Bearer forged"
    assert "cookie" not in sent
    assert "x-forwarded-for" not in sent
    assert sent["idempotency-key"] == "k1"
    assert sent["x-request-id"] == "r1"


def test_the_crm_answer_comes_back_as_is_but_only_safe_headers(client: TestClient, crm: FakeCrm) -> None:
    crm.status = 409
    answer = client.post(f"{GW}{VISIT}/cancel", content=b'{"reason": "x"}')
    assert answer.status_code == 409
    assert answer.headers["retry-after"] == "7"
    assert "x-secret" not in answer.headers


def test_a_redirect_is_not_followed(key: keys.SigningKey) -> None:
    seen: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(302, headers={"location": "http://evil.example/steal"})

    with TestClient(create_app(key, UPSTREAM, transport=httpx.MockTransport(handle))) as c:
        answer = c.get(f"{GW}/free-slots")
    assert answer.status_code == 302
    assert "location" not in answer.headers
    assert seen == [f"{UPSTREAM}/free-slots"]


def test_crm_down_is_502(client: TestClient, crm: FakeCrm) -> None:
    crm.fail = httpx.ConnectError("refused")
    answer = client.get(f"{GW}/free-slots")
    assert answer.status_code == 502
    assert body_of(answer.content)["error"]["code"] == "upstream_unavailable"


def test_body_too_large_is_413(client: TestClient, crm: FakeCrm) -> None:
    answer = client.put(GW + PERSON, content=b"x" * (MAX_BODY + 1))
    assert answer.status_code == 413
    assert crm.calls == []


def test_rate_limit(key: keys.SigningKey, crm: FakeCrm) -> None:
    now = [1_000_000.0]
    app = create_app(key, UPSTREAM, transport=httpx.MockTransport(crm.handle), clock=lambda: now[0])
    with TestClient(app) as c:
        for _ in range(PER_MINUTE):
            assert c.get(f"{GW}/free-slots").status_code == 200
        assert c.get(f"{GW}/free-slots").status_code == 429
        now[0] += 61
        assert c.get(f"{GW}/free-slots").status_code == 200


def test_the_private_key_never_shows_in_logs_or_answers(
    client: TestClient, crm: FakeCrm, key: keys.SigningKey, caplog: pytest.LogCaptureFixture
) -> None:
    raw = key.private.private_bytes(
        serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption()
    )
    with caplog.at_level(logging.DEBUG):
        answer = client.put(GW + PERSON, content=b'{"full_name": "Nguyen Van A", "phone": "0901234567"}')
        crm.fail = httpx.ConnectError("x")
        client.get(f"{GW}/free-slots")
    # only the service's own lines: the test client logs its own requests under another name
    text = "\n".join(r.getMessage() for r in caplog.records if r.name == "crm_signer")
    assert "Nguyen" not in text
    assert "0901234567" not in text
    assert "u123" not in text
    assert raw not in text.encode()
    assert raw not in answer.content
    assert "PUT /contacts/{channel}/{external_id} -> 200" in text


def test_health(client: TestClient) -> None:
    assert client.get("/health").json() == {"ok": True}


# ----------------------------------------------------------------------------------------- keys and cli


def test_keygen_once_prints_the_public_key_and_never_replaces(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "k" / "crm-signer-ed25519.pem"
    assert cli.main(["--key-file", str(path), "keygen"]) == 0
    out = capsys.readouterr().out
    loaded = keys.load(path)
    assert out.strip() == f"PEMA_AGENT_GATEWAY_PUBLIC_KEYS={loaded.x}"
    assert "PRIVATE" not in out
    before = path.read_bytes()
    assert cli.main(["--key-file", str(path), "keygen"]) == 1
    assert path.read_bytes() == before


def test_serve_without_a_key_does_not_start(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["--key-file", str(tmp_path / "missing.pem"), "serve"]) == 1
    assert "keygen" in capsys.readouterr().err
    (tmp_path / "bad.pem").write_bytes(b"not a key")
    assert cli.main(["--key-file", str(tmp_path / "bad.pem"), "serve"]) == 1


def test_the_route_list_is_the_crm_gateway() -> None:
    """The two sides must agree: every gateway route of the CRM and nothing else, each with its permission."""
    from fastapi.routing import APIRoute

    from pema.api.routers.agent_gateway import router
    from pema.clinic.rbac.matrix import AGENT_PERMISSIONS

    crm = {
        (method, route.path.removeprefix(GW))
        for route in router.routes
        if isinstance(route, APIRoute)
        for method in route.methods or ()
    }
    assert {(r.method, r.template) for r in ROUTES} == crm
    assert {r.scope for r in ROUTES} == {p.value for p in AGENT_PERMISSIONS}
