# ported from: prototype/shared/operations-data.js (saveAppointment, setStatus, cancel) behaviours
"""Appointments through the HTTP API: conflict check in the action layer, transitions, doctor limits."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

import httpx
import pytest

from pema.api.clinic_testing import ClientFactory, fresh_start
from pema.clinic.actions.seed_demo import SeedResult

pytestmark = pytest.mark.db


def _body(
    world: SeedResult,
    code: str = "P027",
    doctor: str | None = "doctor.mai",
    start: str | None = None,
    **kw: object,
) -> dict[str, object]:
    body: dict[str, object] = {
        "patient_id": str(world.patients[code]),
        "starts_at": start or fresh_start(),
        "duration_min": 30,
    }
    if doctor:
        body["doctor_id"] = str(world.users[doctor])
    body.update(kw)
    return body


async def _book(client: httpx.AsyncClient, body: dict[str, object]) -> httpx.Response:
    return await client.post("/api/v1/appointments", json=body)


async def test_booking_returns_the_appointment_with_the_patient_code_and_version_one(
    client_factory: ClientFactory, world: SeedResult
) -> None:
    reception = await client_factory("reception.lan")
    response = await _book(reception, _body(world))
    assert response.status_code == 201, response.text
    appt = response.json()
    assert appt["patient_code"] == "P027"
    assert appt["status"] == "booked"
    assert appt["version"] == 1
    assert appt["starts_at"].endswith("+07:00")
    assert appt["created_by"] == str(world.users["reception.lan"])
    assert (await reception.get(f"/api/v1/appointments/{appt['id']}")).json()["id"] == appt["id"]


async def test_the_same_doctor_cannot_be_double_booked_and_the_same_patient_neither(
    client_factory: ClientFactory, world: SeedResult
) -> None:
    """Trùng bác sĩ / Trùng bệnh nhân"""
    reception = await client_factory("reception.lan")
    start = fresh_start(9)
    assert (await _book(reception, _body(world, "P027", "doctor.mai", start))).status_code == 201
    other_patient = await _book(reception, _body(world, "P029", "doctor.mai", start))
    assert other_patient.status_code == 409
    assert other_patient.json()["error"]["code"] == "appointment_conflict"
    assert other_patient.json()["error"]["details"]["conflict"] == "doctor"
    same_patient = await _book(reception, _body(world, "P027", "doctor.an", start))
    assert same_patient.status_code == 409
    assert same_patient.json()["error"]["details"]["conflict"] == "patient"
    # another doctor and another patient at the same time is fine
    assert (await _book(reception, _body(world, "P029", "doctor.an", start))).status_code == 201


async def test_concurrent_bookings_of_the_same_slot_let_exactly_one_through(
    client_factory: ClientFactory, world: SeedResult
) -> None:
    """hai lượt đặt cùng lúc cùng một khung giờ: chỉ một lượt thành công (khóa advisory)"""
    reception = await client_factory("reception.lan")
    start = fresh_start(10)
    results = await asyncio.gather(
        _book(reception, _body(world, "P027", "doctor.mai", start)),
        _book(reception, _body(world, "P029", "doctor.mai", start)),
        _book(reception, _body(world, "P031", "doctor.mai", start)),
    )
    assert sorted(r.status_code for r in results) == [201, 409, 409]


@pytest.mark.parametrize(("hour", "minute"), [(7, 30), (11, 45), (12, 0), (17, 45)])
async def test_outside_the_shift_or_in_the_break_is_a_422(
    client_factory: ClientFactory, world: SeedResult, hour: int, minute: int
) -> None:
    reception = await client_factory("reception.lan")
    response = await _book(reception, _body(world, start=fresh_start(hour, minute)))
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_failed"


async def test_a_past_day_is_refused(client_factory: ClientFactory, world: SeedResult) -> None:
    reception = await client_factory("reception.lan")
    response = await _book(reception, _body(world, start="2026-09-19T10:00:00+07:00"))
    assert response.status_code == 422


async def test_a_naive_datetime_is_refused_by_the_wire_format(
    client_factory: ClientFactory, world: SeedResult
) -> None:
    reception = await client_factory("reception.lan")
    response = await _book(reception, _body(world, start="2027-03-01T10:00:00"))
    assert response.status_code == 422


async def test_reschedule_checks_conflicts_without_colliding_with_itself_and_uses_the_version(
    client_factory: ClientFactory, world: SeedResult
) -> None:
    reception = await client_factory("reception.lan")
    start = datetime.fromisoformat(fresh_start(9))
    a = (await _book(reception, _body(world, "P027", "doctor.mai", start.isoformat()))).json()
    b = (
        await _book(
            reception, _body(world, "P029", "doctor.mai", (start + timedelta(minutes=30)).isoformat())
        )
    ).json()
    # moving A by 15 minutes overlaps B
    clash = await reception.patch(
        f"/api/v1/appointments/{a['id']}",
        json={"version": 1, "starts_at": (start + timedelta(minutes=15)).isoformat()},
    )
    assert clash.status_code == 409
    # moving A by 15 minutes EARLIER overlaps nobody and itself is ignored
    moved = await reception.patch(
        f"/api/v1/appointments/{a['id']}",
        json={"version": 1, "starts_at": (start - timedelta(minutes=15)).isoformat(), "note": "đổi giờ"},
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["version"] == 2
    stale = await reception.patch(f"/api/v1/appointments/{a['id']}", json={"version": 1, "note": "x"})
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "version_conflict"
    assert b["id"]


async def test_reception_walks_an_appointment_through_arrive_start_complete(
    client_factory: ClientFactory, world: SeedResult
) -> None:
    reception = await client_factory("reception.lan")
    appt = (await _book(reception, _body(world))).json()
    base = f"/api/v1/appointments/{appt['id']}"
    arrived = await reception.post(f"{base}/check-in", json={"version": 1})
    assert arrived.json()["status"] == "arrived"
    # a second check-in is an invalid state, not a silent success
    again = await reception.post(f"{base}/check-in", json={"version": 2})
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "invalid_state"
    started = await reception.post(f"{base}/start", json={"version": 2})
    assert started.json()["status"] == "in_progress"
    done = await reception.post(f"{base}/complete", json={"version": 3})
    assert done.json()["status"] == "completed"
    # a finished visit can neither be cancelled nor rescheduled
    assert (await reception.post(f"{base}/cancel", json={"version": 4, "reason": "x"})).status_code == 409
    assert (await reception.patch(base, json={"version": 4, "note": "x"})).status_code == 409


async def test_a_check_in_retried_with_the_same_idempotency_key_returns_the_first_result(
    client_factory: ClientFactory, world: SeedResult
) -> None:
    reception = await client_factory("reception.lan")
    appt = (await _book(reception, _body(world))).json()
    url = f"/api/v1/appointments/{appt['id']}/check-in"
    headers = {"Idempotency-Key": "checkin-1"}
    first = await reception.post(url, json={"version": 1}, headers=headers)
    retry = await reception.post(url, json={"version": 1}, headers=headers)
    assert first.status_code == retry.status_code == 200
    assert retry.json()["status"] == "arrived"


async def test_cancel_needs_a_reason_and_frees_the_slot_miss_frees_it_too(
    client_factory: ClientFactory, world: SeedResult
) -> None:
    reception = await client_factory("reception.lan")
    start = fresh_start(14)
    appt = (await _book(reception, _body(world, "P027", "doctor.mai", start))).json()
    base = f"/api/v1/appointments/{appt['id']}"
    assert (await reception.post(f"{base}/cancel", json={"version": 1})).status_code == 422
    cancelled = await reception.post(f"{base}/cancel", json={"version": 1, "reason": "bệnh nhân bận"})
    assert cancelled.json()["status"] == "cancelled"
    assert cancelled.json()["cancel_reason"] == "bệnh nhân bận"
    assert cancelled.json()["cancelled_at"] is not None
    # the slot is free again
    second = (await _book(reception, _body(world, "P029", "doctor.mai", start))).json()
    missed = await reception.post(f"/api/v1/appointments/{second['id']}/miss", json={"version": 1})
    assert missed.json()["status"] == "missed"
    assert missed.json()["missed_at"] is not None
    assert (await _book(reception, _body(world, "P031", "doctor.mai", start))).status_code == 201


async def test_a_doctor_edits_only_their_own_appointments(
    client_factory: ClientFactory, world: SeedResult
) -> None:
    """Sửa lịch/check-in: bác sĩ giới hạn"""
    reception = await client_factory("reception.lan")
    mai = await client_factory("doctor.mai")
    theirs = (await _book(reception, _body(world, "P027", "doctor.an"))).json()
    mine = (await _book(reception, _body(world, "P029", "doctor.mai"))).json()
    assert (
        await mai.post(f"/api/v1/appointments/{theirs['id']}/check-in", json={"version": 1})
    ).status_code == 403
    assert (
        await mai.patch(f"/api/v1/appointments/{theirs['id']}", json={"version": 1, "note": "x"})
    ).status_code == 403
    assert (
        await mai.post(f"/api/v1/appointments/{mine['id']}/check-in", json={"version": 1})
    ).status_code == 200
    # a doctor books only for themselves
    assert (await _book(mai, _body(world, "P031", "doctor.an"))).status_code == 403
    assert (await _book(mai, _body(world, "P031", "doctor.mai"))).status_code == 201
    # but may read every appointment
    assert (await mai.get(f"/api/v1/appointments/{theirs['id']}")).status_code == 200


async def test_the_booked_doctor_must_be_an_active_doctor_of_the_clinic(
    client_factory: ClientFactory, world: SeedResult
) -> None:
    reception = await client_factory("reception.lan")
    response = await _book(reception, _body(world, doctor="cs.thu"))
    assert response.status_code == 422


async def test_cs_staff_books_only_through_a_crm_task(
    client_factory: ClientFactory, world: SeedResult
) -> None:
    cs = await client_factory("cs.maianh")
    assert (await _book(cs, _body(world))).status_code == 403
    tasks = (await cs.get("/api/v1/crm/tasks", params={"patient_id": str(world.patients["P027"])})).json()
    task_id = tasks["items"][0]["id"]
    linked = await _book(cs, _body(world, "P027", "doctor.mai", crm_task_id=task_id))
    assert linked.status_code == 201, linked.text
    task = (await cs.get(f"/api/v1/crm/tasks/{task_id}")).json()
    assert task["related_appointment_id"] == linked.json()["id"]
    # a task of another patient cannot be used
    wrong = await _book(cs, _body(world, "P029", "doctor.mai", crm_task_id=task_id))
    assert wrong.status_code == 422


async def test_listing_filters_by_status_patient_and_time_window(
    client_factory: ClientFactory, world: SeedResult
) -> None:
    reception = await client_factory("reception.lan")
    start = fresh_start(9)
    appt = (await _book(reception, _body(world, "P032", "doctor.mai", start))).json()
    params = {"patient_id": str(world.patients["P032"]), "appointment_status": "booked"}
    page = (await reception.get("/api/v1/appointments", params=params)).json()
    assert appt["id"] in [a["id"] for a in page["items"]]
    window_start = datetime.fromisoformat(start) - timedelta(hours=1)
    window = (
        await reception.get(
            "/api/v1/appointments",
            params={
                "starts_from": window_start.isoformat(),
                "starts_to": (window_start + timedelta(hours=3)).isoformat(),
            },
        )
    ).json()
    assert [a["id"] for a in window["items"]] == [appt["id"]]
