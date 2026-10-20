# ruff: noqa: PT018
"""The agent gateway (docs/PLAN-crm-plugin.md): the agent's key opens it and nothing else, and every call acts
for the person of one chat only (rules L2-L4; tests T6, T8)."""

from __future__ import annotations

import hashlib
import itertools
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from datetime import date, datetime, timedelta
from typing import Any
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.engine import Engine

from pema.api.agent_gateway_auth import WRITES_PER_HOUR, reset_agent_gateway_limits
from pema.api.clinic_testing import ClientFactory
from pema.clinic.actions.seed_demo import SeedResult
from pema.config.env import get_settings
from pema_contracts.common import VN_TZ

pytestmark = pytest.mark.db

KEY = "agent-gateway-test-key-0123456789abcdef"  # throwaway test value only
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


@pytest.fixture
def gateway_on(monkeypatch: pytest.MonkeyPatch, jwt_env: None) -> Iterator[None]:
    monkeypatch.setenv("PEMA_AGENT_GATEWAY_KEY_SHA256", hashlib.sha256(KEY.encode()).hexdigest())
    get_settings.cache_clear()
    reset_agent_gateway_limits()
    yield
    get_settings.cache_clear()
    reset_agent_gateway_limits()


@pytest_asyncio.fixture
async def agent(app: FastAPI, gateway_on: None, world: SeedResult) -> AsyncIterator[httpx.AsyncClient]:
    """The agent's client, on the seeded clinic (three doctors)."""
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test", headers={"Authorization": f"Bearer {KEY}"}
    ) as http:
        yield http


Save = Callable[..., Awaitable[str]]


@pytest.fixture
def saved(agent: httpx.AsyncClient) -> Save:
    """A person with a saved contact; returns their path."""

    async def make(
        name: str = "Khách thử (mẫu)", phone: str = "0912 000 111", consent: bool | None = None
    ) -> str:
        path = person()
        response = await agent.put(
            path, json={"full_name": name, "phone": phone, "messages_consent": consent}
        )
        assert response.status_code == 200, response.text
        return path

    return make


async def _book(
    agent: httpx.AsyncClient, path: str, starts_at: str, key: str | None = None
) -> httpx.Response:
    return await agent.post(
        f"{path}/appointments",
        json={"starts_at": starts_at, "duration_min": 30, "note": "Tư vấn da"},
        headers={"Idempotency-Key": key or uuid4().hex},
    )


def _rows(admin: Engine, sql: str, **params: Any) -> list[Any]:
    with admin.connect() as conn:
        return list(conn.execute(text(sql), params).all())


# ------------------------------------------------------------------ T6: the key, and only the key


async def test_the_gateway_is_off_without_a_key_hash(app: FastAPI) -> None:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        response = await http.get(
            f"{GW}/free-slots", params={"day_from": "2027-01-04"}, headers={"Authorization": f"Bearer {KEY}"}
        )
    assert response.status_code == 404


async def test_a_wrong_key_or_none_is_refused(app: FastAPI, gateway_on: None) -> None:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        none = await http.get(f"{GW}/free-slots", params={"day_from": "2027-01-04"})
        wrong = await http.get(
            f"{GW}/free-slots", params={"day_from": "2027-01-04"}, headers={"Authorization": "Bearer nope"}
        )
    assert (none.status_code, wrong.status_code) == (401, 401)


async def test_a_staff_cookie_does_not_open_the_gateway(
    client_factory: ClientFactory, gateway_on: None, world: SeedResult
) -> None:
    """T6: the owner's session is no agent key"""
    owner = await client_factory("owner")
    response = await owner.get(f"{GW}/free-slots", params={"day_from": "2027-01-04"})
    assert response.status_code == 401


async def test_the_key_opens_no_staff_route(agent: httpx.AsyncClient, world: SeedResult) -> None:
    """T6: the agent's key on the CRM's own routes is an anonymous caller"""
    for path in (
        "/api/v1/patients",
        "/api/v1/appointments",
        f"/api/v1/patients/{world.patients['P027']}/360",
    ):
        assert (await agent.get(path)).status_code == 401, path
    created = await agent.post("/api/v1/patients", json={"full_name": "X"})
    assert created.status_code == 401


# ------------------------------------------------------------------ free times


async def test_free_times_skip_the_break_and_close_when_every_doctor_is_taken(
    agent: httpx.AsyncClient, client_factory: ClientFactory, world: SeedResult
) -> None:
    day = free_day()
    first = (await agent.get(f"{GW}/free-slots", params={"day_from": day.isoformat()})).json()
    starts = [s[11:16] for s in first["days"][0]["starts"]]
    assert starts[0] == "08:00" and starts[-1] == "17:30"
    assert "11:45" not in starts and "12:30" not in starts and "13:00" in starts
    reception = await client_factory("reception.lan")
    codes = ["P027", "P026", "P025"][:DOCTORS]
    booked = [
        await reception.post(
            "/api/v1/appointments",
            json={"patient_id": str(world.patients[c]), "starts_at": at(day, 9), "duration_min": 30},
        )
        for c in codes
    ]
    assert [r.status_code for r in booked] == [201] * DOCTORS, booked[-1].text
    full = (await agent.get(f"{GW}/free-slots", params={"day_from": day.isoformat()})).json()
    starts = [s[11:16] for s in full["days"][0]["starts"]]
    assert "09:00" not in starts and "08:45" not in starts
    assert "08:30" in starts and "09:30" in starts
    body = str(full)
    assert "P027" not in body and "patient" not in body
    cancel = booked[0].json()
    await reception.post(f"/api/v1/appointments/{cancel['id']}/cancel", json={"version": 1, "reason": "test"})
    again = (await agent.get(f"{GW}/free-slots", params={"day_from": day.isoformat()})).json()
    assert "09:00" in [s[11:16] for s in again["days"][0]["starts"]]


async def test_a_past_day_starts_from_today_and_never_offers_a_past_time(agent: httpx.AsyncClient) -> None:
    response = await agent.get(f"{GW}/free-slots", params={"day_from": "2020-01-01", "days": 1})
    day = response.json()["days"][0]
    assert day["day"] == "2026-09-20"  # the demo day, 09:00: at least 30 minutes ahead
    assert all(s[11:16] >= "09:30" for s in day["starts"])


# ------------------------------------------------------------------ contacts


async def test_the_first_save_makes_a_patient_and_a_later_one_changes_nothing(
    agent: httpx.AsyncClient, admin: Engine
) -> None:
    path = person()
    first = await agent.put(path, json={"full_name": "Lan (mẫu)", "phone": "+84 912.345.678"})
    second = await agent.put(path, json={"full_name": "Người khác", "phone": "0999999999"})
    assert first.json() == {"created": True, "messages_consent": None}
    assert second.json() == {"created": False, "messages_consent": None}
    external_id = path.rsplit("/", 1)[1]
    rows = _rows(
        admin,
        "SELECT p.full_name, p.phone, p.source FROM clinic.patient_channel c "
        "JOIN clinic.patient p ON p.id = c.patient_id WHERE c.external_id = :e",
        e=external_id,
    )
    assert rows == [("Lan (mẫu)", "0912345678", "agent:zalo-test")]


async def test_a_phone_of_an_existing_patient_makes_a_new_patient_not_a_link_to_theirs(
    agent: httpx.AsyncClient, admin: Engine, world: SeedResult
) -> None:
    """Giving someone's number never makes you them."""
    phone = _rows(admin, "SELECT phone FROM clinic.patient WHERE id = :p", p=world.patients["P027"])[0][0]
    path = person()
    response = await agent.put(path, json={"full_name": "Kẻ mạo danh", "phone": "0912000222"})
    assert response.json()["created"] is True
    linked = _rows(
        admin,
        "SELECT patient_id FROM clinic.patient_channel WHERE external_id = :e",
        e=path.rsplit("/", 1)[1],
    )
    assert linked[0][0] != world.patients["P027"]
    assert phone  # the seed patient has one; the new contact did not match on anything


async def test_a_wrong_phone_is_refused(agent: httpx.AsyncClient) -> None:
    response = await agent.put(person(), json={"full_name": "Lan", "phone": "12345"})
    assert response.status_code == 422


async def test_the_consent_to_messages_is_recorded_once_per_change(
    agent: httpx.AsyncClient, admin: Engine
) -> None:
    path = person()
    for consent in (True, True, None, False):
        await agent.put(path, json={"full_name": "Lan", "phone": "0912000333", "messages_consent": consent})
    rows = _rows(
        admin,
        "SELECT s.granted, s.source FROM clinic.consent s JOIN clinic.patient_channel c "
        "ON c.patient_id = s.patient_id WHERE c.external_id = :e ORDER BY s.created_at, s.id",
        e=path.rsplit("/", 1)[1],
    )
    assert rows == [(True, "agent:zalo-test"), (False, "agent:zalo-test")]


async def test_writes_of_one_person_are_limited_per_hour(agent: httpx.AsyncClient) -> None:
    path = person()
    codes = [
        (await agent.put(path, json={"full_name": "Lan", "phone": "0912000444"})).status_code
        for _ in range(WRITES_PER_HOUR + 1)
    ]
    assert codes[:WRITES_PER_HOUR] == [200] * WRITES_PER_HOUR
    assert codes[-1] == 429


# ------------------------------------------------------------------ booking


async def test_booking_needs_a_saved_contact_and_a_key(agent: httpx.AsyncClient, saved: Save) -> None:
    day = free_day()
    assert (await _book(agent, person(), at(day, 9))).status_code == 409
    path = await saved()
    keyless = await agent.post(f"{path}/appointments", json={"starts_at": at(day, 9)})
    assert keyless.status_code == 422


async def test_a_booking_is_made_once_whatever_the_retries(
    agent: httpx.AsyncClient, saved: Save, admin: Engine
) -> None:
    path = await saved()
    day = free_day()
    first = await _book(agent, path, at(day, 10), key="same-key-1")
    again = await _book(agent, path, at(day, 10), key="same-key-1")
    assert first.status_code == 201, first.text
    assert again.json()["id"] == first.json()["id"]
    visit = first.json()
    assert visit["status"] == "booked"
    assert set(visit) == {"id", "starts_at", "duration_min", "status"}
    rows = _rows(
        admin, "SELECT doctor_id, created_by, note FROM clinic.appointment WHERE id = :i", i=visit["id"]
    )
    assert rows == [(None, None, "Tư vấn da")]


async def test_a_person_holds_at_most_two_coming_visits(agent: httpx.AsyncClient, saved: Save) -> None:
    path = await saved()
    codes = [(await _book(agent, path, at(free_day(), 9))).status_code for _ in range(3)]
    assert codes == [201, 201, 409]


async def test_a_full_time_is_refused(
    agent: httpx.AsyncClient, saved: Save, client_factory: ClientFactory, world: SeedResult
) -> None:
    day = free_day()
    reception = await client_factory("reception.lan")
    for code in ["P027", "P026", "P025"][:DOCTORS]:
        await reception.post(
            "/api/v1/appointments", json={"patient_id": str(world.patients[code]), "starts_at": at(day, 14)}
        )
    response = await _book(agent, await saved(), at(day, 14))
    assert response.status_code == 409
    assert response.json()["error"]["details"]["conflict"] == "capacity"


async def test_a_time_too_soon_or_in_the_break_is_refused(agent: httpx.AsyncClient, saved: Save) -> None:
    path = await saved()
    soon = await _book(agent, path, "2026-09-20T09:15:00+07:00")  # the demo clock is 09:00
    lunch = await _book(agent, path, at(free_day(), 12))
    assert (soon.status_code, lunch.status_code) == (422, 422)


# ------------------------------------------------------------------ T8: one person never touches another's visit


async def test_another_person_cannot_see_or_change_a_visit(agent: httpx.AsyncClient, saved: Save) -> None:
    owner_path, other_path = await saved(), await saved()
    visit = (await _book(agent, owner_path, at(free_day(), 9))).json()
    assert (await agent.get(f"{other_path}/appointments")).json() == []
    base = f"{other_path}/appointments/{visit['id']}"
    attempts = [
        await agent.post(f"{base}/confirm"),
        await agent.post(f"{base}/cancel", json={"reason": "x"}),
        await agent.post(
            f"{base}/reschedule", json={"starts_at": at(free_day(), 10)}, headers={"Idempotency-Key": "k"}
        ),
    ]
    assert [a.status_code for a in attempts] == [404, 404, 404]
    mine = (await agent.get(f"{owner_path}/appointments")).json()
    assert [v["status"] for v in mine] == ["booked"]


async def test_a_person_without_a_contact_has_no_visits(agent: httpx.AsyncClient) -> None:
    assert (await agent.get(f"{person()}/appointments")).json() == []


# ------------------------------------------------------------------ confirm, move, cancel


async def test_confirm_then_cancel_a_coming_visit(
    agent: httpx.AsyncClient, saved: Save, admin: Engine
) -> None:
    path = await saved()
    visit = (await _book(agent, path, at(free_day(), 9))).json()
    base = f"{path}/appointments/{visit['id']}"
    confirmed = await agent.post(f"{base}/confirm")
    twice = await agent.post(f"{base}/confirm")
    cancelled = await agent.post(f"{base}/cancel", json={"reason": "bận việc"})
    after = await agent.post(f"{base}/confirm")
    assert (confirmed.json()["status"], twice.json()["status"]) == ("confirmed", "confirmed")
    assert cancelled.json()["status"] == "cancelled"
    assert after.status_code == 409
    reason = _rows(admin, "SELECT cancel_reason FROM clinic.appointment WHERE id = :i", i=visit["id"])
    assert reason == [("Khách hủy qua chat: bận việc",)]


async def test_a_visit_moves_once_per_key_and_at_most_three_times(
    agent: httpx.AsyncClient, saved: Save
) -> None:
    path = await saved()
    day = free_day()
    visit = (await _book(agent, path, at(day, 8))).json()
    base = f"{path}/appointments/{visit['id']}/reschedule"

    async def move(hour: int, key: str) -> httpx.Response:
        return await agent.post(base, json={"starts_at": at(day, hour)}, headers={"Idempotency-Key": key})

    first = await move(9, "m1")
    repeat = await move(15, "m1")
    assert first.json()["starts_at"][11:16] == "09:00"
    assert repeat.json()["starts_at"][11:16] == "09:00"
    assert [(await move(h, f"m{h}")).status_code for h in (10, 11, 14)] == [200, 200, 409]


# ------------------------------------------------------------------ reminders


async def test_reminders_list_only_people_who_agreed_and_name_no_one(
    agent: httpx.AsyncClient, saved: Save
) -> None:
    yes, no = await saved(consent=True), await saved(consent=False)
    soon = "2026-09-21T10:00:00+07:00"  # 25 hours after the demo clock (2026-09-20 09:00)
    later = "2026-09-23T10:00:00+07:00"
    yes_visit = (await _book(agent, yes, soon)).json()
    await _book(agent, yes, later)
    await _book(agent, no, "2026-09-21T10:30:00+07:00")
    listed = (await agent.get(f"{GW}/reminders", params={"hours": 26})).json()
    mine = [r for r in listed if r["external_id"] in {yes.rsplit("/", 1)[1], no.rsplit("/", 1)[1]}]
    assert [r["appointment_id"] for r in mine] == [yes_visit["id"]]
    assert set(mine[0]) == {
        "appointment_id",
        "channel",
        "external_id",
        "starts_at",
        "duration_min",
        "status",
        "updated_at",
    }


# ------------------------------------------------------------------ audit


async def test_every_write_is_audited_as_the_agent_and_without_pii(
    agent: httpx.AsyncClient, saved: Save, admin: Engine
) -> None:
    path = await saved(consent=True)
    visit = (await _book(agent, path, at(free_day(), 9))).json()
    await agent.post(f"{path}/appointments/{visit['id']}/confirm")
    patient = _rows(
        admin,
        "SELECT patient_id FROM clinic.patient_channel WHERE external_id = :e",
        e=path.rsplit("/", 1)[1],
    )[0][0]
    rows = _rows(
        admin,
        "SELECT action, actor_type, details FROM clinic.audit_log "
        "WHERE entity_id IN (:p, :a) OR details->>'patient_id' = :p ORDER BY id",
        p=str(patient),
        a=visit["id"],
    )
    actions = [r[0] for r in rows]
    assert {"patient.create", "patient_channel.create", "consent.record", "appointment.create"} <= set(
        actions
    )
    assert "appointment.confirm" in actions
    assert {r[1] for r in rows} == {"agent"}
    assert all(r[2].get("source") == "agent" for r in rows)
    flat = str([r[2] for r in rows])
    assert "0912000111" not in flat and "Khách thử" not in flat
