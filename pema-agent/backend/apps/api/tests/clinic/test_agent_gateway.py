# ruff: noqa: PT018
"""The agent gateway (docs/PLAN-crm-plugin.md): a token signed by crm-signer opens it and nothing else, and
every call acts for the person of one chat only (rules L2-L4; tests T6, T8, step 1b)."""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import timedelta

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.engine import Engine

from pema.api.agent_gateway_auth import WRITES_PER_HOUR
from pema.api.clinic_testing import DEMO_NOW, ClientFactory
from pema.api.gateway_testing import (
    DOCTORS,
    GW,
    KEY,
    OTHER_KEY,
    Save,
    at,
    bearer,
    book,
    free_day,
    person,
    public,
    rows,
    token,
)
from pema.clinic.actions.seed_demo import SeedResult
from pema.config.env import get_settings

pytestmark = pytest.mark.db

# ------------------------------------------------------------------ T6: the token, and only the token


async def test_the_gateway_is_off_without_a_public_key(app: FastAPI) -> None:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        response = await http.get(
            f"{GW}/free-slots", params={"day_from": "2027-01-04"}, headers=bearer(token())
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
    """T6: the owner's session is no agent token"""
    owner = await client_factory("owner")
    response = await owner.get(f"{GW}/free-slots", params={"day_from": "2027-01-04"})
    assert response.status_code == 401


async def test_the_token_opens_no_staff_route(agent: httpx.AsyncClient, world: SeedResult) -> None:
    """T6: the agent's token on the CRM's own routes is an anonymous caller"""
    for path in (
        "/api/v1/patients",
        "/api/v1/appointments",
        f"/api/v1/patients/{world.patients['P027']}/360",
    ):
        assert (await agent.get(path)).status_code == 401, path
    created = await agent.post("/api/v1/patients", json={"full_name": "X"})
    assert created.status_code == 401


# ------------------------------------------------------------------ step 1b: what a token must be


async def _free_slots_with(app: FastAPI, value: str) -> int:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        response = await http.get(
            f"{GW}/free-slots", params={"day_from": "2027-01-04"}, headers=bearer(value)
        )
    return response.status_code


def _expired() -> str:
    now = int(time.time())
    return token(iat=now - 600, exp=now - 300)


@pytest.mark.parametrize(
    ("label", "make"),
    [
        ("expired", _expired),
        ("lives too long", lambda: token(exp=int(time.time()) + 3600)),
        ("SSO audience of the agent", lambda: token(aud="pema-agent")),
        ("another issuer", lambda: token(iss="pema-clinic")),
        ("a key the API does not know", lambda: token(OTHER_KEY)),
        ("no jti", lambda: token(jti=None)),
        ("no expiry", lambda: token(exp=None)),
    ],
)
async def test_a_token_that_is_not_crm_signers_short_one_is_refused(
    app: FastAPI, gateway_on: None, world: SeedResult, label: str, make: Callable[[], str]
) -> None:
    assert await _free_slots_with(app, make()) == 401, label


async def test_a_token_is_used_once(app: FastAPI, gateway_on: None, world: SeedResult) -> None:
    once = token()
    assert (await _free_slots_with(app, once), await _free_slots_with(app, once)) == (200, 401)


async def test_a_route_needs_its_own_permission_in_the_scope(
    app: FastAPI, gateway_on: None, world: SeedResult
) -> None:
    assert await _free_slots_with(app, token(scope="agent.booking.write agent.reminders.read")) == 403
    assert await _free_slots_with(app, token(scope="agent.slots.read")) == 200


async def test_two_public_keys_are_accepted_while_a_key_is_changed(
    app: FastAPI, gateway_on: None, world: SeedResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PEMA_AGENT_GATEWAY_PUBLIC_KEYS", f"{public(KEY)}, {public(OTHER_KEY)}")
    get_settings.cache_clear()
    first, second = await _free_slots_with(app, token(KEY)), await _free_slots_with(app, token(OTHER_KEY))
    assert (first, second) == (200, 200)


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
    found = rows(
        admin,
        "SELECT p.full_name, p.phone, p.source FROM clinic.patient_channel c "
        "JOIN clinic.patient p ON p.id = c.patient_id WHERE c.external_id = :e",
        e=external_id,
    )
    assert found == [("Lan (mẫu)", "0912345678", "agent:zalo-test")]


async def test_a_phone_of_an_existing_patient_makes_a_new_patient_not_a_link_to_theirs(
    agent: httpx.AsyncClient, admin: Engine, world: SeedResult
) -> None:
    """Giving someone's number never makes you them."""
    phone = rows(admin, "SELECT phone FROM clinic.patient WHERE id = :p", p=world.patients["P027"])[0][0]
    path = person()
    response = await agent.put(path, json={"full_name": "Kẻ mạo danh", "phone": "0912000222"})
    assert response.json()["created"] is True
    linked = rows(
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
    found = rows(
        admin,
        "SELECT s.granted, s.source FROM clinic.consent s JOIN clinic.patient_channel c "
        "ON c.patient_id = s.patient_id WHERE c.external_id = :e ORDER BY s.created_at, s.id",
        e=path.rsplit("/", 1)[1],
    )
    assert found == [(True, "agent:zalo-test"), (False, "agent:zalo-test")]


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
    assert (await book(agent, person(), at(day, 9))).status_code == 409
    path = await saved()
    keyless = await agent.post(f"{path}/appointments", json={"starts_at": at(day, 9)})
    assert keyless.status_code == 422


async def test_a_booking_is_made_once_whatever_the_retries(
    agent: httpx.AsyncClient, saved: Save, admin: Engine
) -> None:
    path = await saved()
    day = free_day()
    first = await book(agent, path, at(day, 10), key="same-key-1")
    again = await book(agent, path, at(day, 10), key="same-key-1")
    assert first.status_code == 201, first.text
    assert again.json()["id"] == first.json()["id"]
    visit = first.json()
    assert visit["status"] == "booked"
    assert set(visit) == {"id", "starts_at", "duration_min", "status"}
    found = rows(
        admin, "SELECT doctor_id, created_by, note FROM clinic.appointment WHERE id = :i", i=visit["id"]
    )
    assert found == [(None, None, "Tư vấn da")]


async def test_a_person_holds_at_most_two_coming_visits(agent: httpx.AsyncClient, saved: Save) -> None:
    path = await saved()
    codes = [(await book(agent, path, at(free_day(), 9))).status_code for _ in range(3)]
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
    response = await book(agent, await saved(), at(day, 14))
    assert response.status_code == 409
    assert response.json()["error"]["details"]["conflict"] == "capacity"


async def test_a_time_too_soon_or_in_the_break_is_refused(agent: httpx.AsyncClient, saved: Save) -> None:
    path = await saved()
    soon = await book(agent, path, "2026-09-20T09:15:00+07:00")  # the demo clock is 09:00
    lunch = await book(agent, path, at(free_day(), 12))
    assert (soon.status_code, lunch.status_code) == (422, 422)


# ------------------------------------------------------------------ T8: one person never touches another's visit


async def test_another_person_cannot_see_or_change_a_visit(agent: httpx.AsyncClient, saved: Save) -> None:
    owner_path, other_path = await saved(), await saved()
    visit = (await book(agent, owner_path, at(free_day(), 9))).json()
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


async def test_a_visit_just_changed_is_listed_after_the_coming_ones_without_its_reason(
    agent: httpx.AsyncClient, saved: Save, admin: Engine
) -> None:
    """The agent says "that visit was cancelled" instead of guessing it was never saved; staff's reason stays here."""
    path, other_path = await saved(), await saved()
    gone = (await book(agent, path, at(free_day(), 9))).json()
    kept = (await book(agent, path, at(free_day(), 10))).json()
    await agent.post(f"{path}/appointments/{gone['id']}/cancel", json={"reason": "bận việc"})

    listed = (await agent.get(f"{path}/appointments")).json()

    assert [(v["id"], v["status"]) for v in listed] == [(kept["id"], "booked"), (gone["id"], "cancelled")]
    assert all(set(v) == {"id", "starts_at", "duration_min", "status"} for v in listed)
    assert (await agent.get(f"{other_path}/appointments")).json() == []
    assert "bận việc" not in str(listed)
    assert rows(admin, "SELECT count(*) FROM clinic.appointment WHERE id = :i", i=gone["id"]) == [(1,)]


@pytest.mark.parametrize("status", ["arrived", "in_progress"])
async def test_a_visit_staff_marked_arrived_or_in_progress_does_not_vanish(
    agent: httpx.AsyncClient, saved: Save, admin: Engine, status: str
) -> None:
    """Reception marks "đã đến" as a matter of course: the person must not hear that there is no visit."""
    path = await saved()
    visit = (await book(agent, path, at(free_day(), 9))).json()
    with admin.begin() as conn:
        conn.execute(
            text("UPDATE clinic.appointment SET status = :s WHERE id = :i"), {"s": status, "i": visit["id"]}
        )

    listed = (await agent.get(f"{path}/appointments")).json()

    assert [(v["id"], v["status"]) for v in listed] == [(visit["id"], status)]


async def test_only_the_last_three_changed_visits_within_a_week_are_listed(
    agent: httpx.AsyncClient, saved: Save, admin: Engine
) -> None:
    path = await saved()
    ids: list[str] = []
    for hour in (9, 10, 11, 14):
        visit = (await book(agent, path, at(free_day(), hour))).json()
        await agent.post(f"{path}/appointments/{visit['id']}/cancel", json={"reason": "x"})
        ids.append(visit["id"])
    assert len((await agent.get(f"{path}/appointments")).json()) == 3

    eight_days_ago = DEMO_NOW - timedelta(days=8)  # the tests' clock is the demo day, not the database's
    with admin.begin() as conn:  # the newest of them, made to look closed eight days ago
        conn.execute(text("SET LOCAL session_replication_role = replica"))  # a trigger sets updated_at
        conn.execute(
            text("UPDATE clinic.appointment SET updated_at = :t WHERE id = :i"),
            {"t": eight_days_ago, "i": ids[-1]},
        )
    listed = (await agent.get(f"{path}/appointments")).json()

    assert len(listed) == 3
    assert ids[-1] not in [v["id"] for v in listed]


# ------------------------------------------------------------------ confirm, move, cancel


async def test_confirm_then_cancel_a_coming_visit(
    agent: httpx.AsyncClient, saved: Save, admin: Engine
) -> None:
    path = await saved()
    visit = (await book(agent, path, at(free_day(), 9))).json()
    base = f"{path}/appointments/{visit['id']}"
    confirmed = await agent.post(f"{base}/confirm")
    twice = await agent.post(f"{base}/confirm")
    cancelled = await agent.post(f"{base}/cancel", json={"reason": "bận việc"})
    after = await agent.post(f"{base}/confirm")
    assert (confirmed.json()["status"], twice.json()["status"]) == ("confirmed", "confirmed")
    assert cancelled.json()["status"] == "cancelled"
    assert after.status_code == 409
    reason = rows(admin, "SELECT cancel_reason FROM clinic.appointment WHERE id = :i", i=visit["id"])
    assert reason == [("Khách hủy qua chat: bận việc",)]


async def test_a_visit_moves_once_per_key_and_at_most_three_times(
    agent: httpx.AsyncClient, saved: Save
) -> None:
    path = await saved()
    day = free_day()
    visit = (await book(agent, path, at(day, 8))).json()
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
    yes_visit = (await book(agent, yes, soon)).json()
    await book(agent, yes, later)
    await book(agent, no, "2026-09-21T10:30:00+07:00")
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
    visit = (await book(agent, path, at(free_day(), 9))).json()
    await agent.post(f"{path}/appointments/{visit['id']}/confirm")
    patient = rows(
        admin,
        "SELECT patient_id FROM clinic.patient_channel WHERE external_id = :e",
        e=path.rsplit("/", 1)[1],
    )[0][0]
    audited = rows(
        admin,
        "SELECT action, actor_type, details FROM clinic.audit_log "
        "WHERE entity_id IN (:p, :a) OR details->>'patient_id' = :p ORDER BY id",
        p=str(patient),
        a=visit["id"],
    )
    actions = [r[0] for r in audited]
    assert {"patient.create", "patient_channel.create", "consent.record", "appointment.create"} <= set(
        actions
    )
    assert "appointment.confirm" in actions
    assert {r[1] for r in audited} == {"agent"}
    assert all(r[2].get("source") == "agent" for r in audited)
    flat = str([r[2] for r in audited])
    assert "0912000111" not in flat and "Khách thử" not in flat
