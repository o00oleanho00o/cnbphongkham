# ported from: prototype/shared/operations-ui.js (schedule, suggest) and crm-ui.js (dashboard) behaviours
"""Package U step U2: the day/week board, the confirm transition, the first free slot, the dashboard KPIs and
what a status change tells the CRM. Demo day 2026-09-20 (Sunday), clock frozen at 09:00."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime, timedelta
from typing import Any
from uuid import UUID

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine

from pema.api.clinic_testing import ClientFactory, fresh_start
from pema.clinic.actions import appointment_events
from pema.clinic.actions.appointment_events import AppointmentChange
from pema.clinic.actions.dashboard import percent, range_days
from pema.clinic.actions.seed_demo import DEMO_DAY, SeedResult
from pema.clinic.crm_rules.runner import CrmRulesRunner
from pema.clinic.crm_rules.sql_store import SqlCrmRuleStore
from pema.clinic.crm_rules.testing import FakeScheduler
from pema.core.db import ClinicDatabase
from pema_contracts.common import VN_TZ
from pema_contracts.dashboard import DashboardRange

pytestmark = pytest.mark.db


def _same_day(start: str, hour: int, minute: int = 0) -> str:
    return datetime.fromisoformat(start).replace(hour=hour, minute=minute).isoformat()


def _body(world: SeedResult, code: str, doctor: str, start: str, minutes: int = 30) -> dict[str, object]:
    return {
        "patient_id": str(world.patients[code]),
        "doctor_id": str(world.users[doctor]),
        "starts_at": start,
        "duration_min": minutes,
    }


async def _book(client: httpx.AsyncClient, body: dict[str, object]) -> dict[str, Any]:
    response = await client.post("/api/v1/appointments", json=body)
    assert response.status_code == 201, response.text
    return response.json()


async def _schedule(client: httpx.AsyncClient, day: str, **params: str) -> dict[str, Any]:
    response = await client.get("/api/v1/appointments/schedule", params={"day": day, **params})
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture
def seen_changes() -> Iterator[list[AppointmentChange]]:
    changes: list[AppointmentChange] = []
    appointment_events.install_listener(changes.append)
    yield changes
    appointment_events.install_listener(None)


# ---------------------------------------------------------------------------------------------- confirm


async def test_confirm_moves_booked_to_confirmed_and_only_from_booked(
    client_factory: ClientFactory, world: SeedResult
) -> None:
    """setStatus(id, 'confirmed'): Đặt hẹn -> Đã xác nhận, once."""
    reception = await client_factory("reception.lan")
    appt = await _book(reception, _body(world, "P027", "doctor.mai", fresh_start()))
    base = f"/api/v1/appointments/{appt['id']}"
    confirmed = await reception.post(f"{base}/confirm", json={"version": 1})
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == "confirmed"
    again = await reception.post(f"{base}/confirm", json={"version": 2})
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "invalid_state"
    stale = await reception.post(f"{base}/check-in", json={"version": 1})
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "version_conflict"
    assert (await reception.post(f"{base}/check-in", json={"version": 2})).json()["status"] == "arrived"


async def test_cs_staff_cannot_confirm_and_a_doctor_confirms_only_their_own(
    client_factory: ClientFactory, world: SeedResult
) -> None:
    reception = await client_factory("reception.lan")
    cs = await client_factory("cs.maianh")
    mai = await client_factory("doctor.mai")
    theirs = await _book(reception, _body(world, "P027", "doctor.an", fresh_start()))
    mine = await _book(reception, _body(world, "P029", "doctor.mai", fresh_start()))
    assert (
        await cs.post(f"/api/v1/appointments/{mine['id']}/confirm", json={"version": 1})
    ).status_code == 403
    assert (
        await mai.post(f"/api/v1/appointments/{theirs['id']}/confirm", json={"version": 1})
    ).status_code == 403
    assert (
        await mai.post(f"/api/v1/appointments/{mine['id']}/confirm", json={"version": 1})
    ).status_code == 200


async def test_the_full_reception_flow_ends_completed_and_writes_one_audit_row_per_step(
    client_factory: ClientFactory, world: SeedResult, admin: Engine
) -> None:
    """booked -> confirmed -> arrived -> in_progress -> completed, each step audited with from/to."""
    reception = await client_factory("reception.lan")
    appt = await _book(reception, _body(world, "P027", "doctor.mai", fresh_start()))
    base = f"/api/v1/appointments/{appt['id']}"
    for version, verb, status in (
        (1, "confirm", "confirmed"),
        (2, "check-in", "arrived"),
        (3, "start", "in_progress"),
        (4, "complete", "completed"),
    ):
        response = await reception.post(f"{base}/{verb}", json={"version": version})
        assert response.json()["status"] == status
    with admin.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT action, details->>'from', details->>'to' FROM clinic.audit_log "
                "WHERE entity_id = :i AND action LIKE 'appointment.%' ORDER BY id"
            ),
            {"i": appt["id"]},
        ).all()
    assert [(a, f, t) for a, f, t in rows] == [
        ("appointment.create", None, None),
        ("appointment.confirm", "booked", "confirmed"),
        ("appointment.check_in", "confirmed", "arrived"),
        ("appointment.start", "arrived", "in_progress"),
        ("appointment.complete", "in_progress", "completed"),
    ]


# ----------------------------------------------------------------------------------------------- board


async def test_the_day_view_lists_the_day_with_names_and_every_status(
    client_factory: ClientFactory, world: SeedResult
) -> None:
    reception = await client_factory("reception.lan")
    start = fresh_start(9)
    day = start[:10]
    first = await _book(reception, _body(world, "P027", "doctor.mai", start))
    second = await _book(reception, _body(world, "P029", "doctor.an", _same_day(start, 9)))
    await reception.post(f"/api/v1/appointments/{second['id']}/cancel", json={"version": 1, "reason": "bận"})
    board = await _schedule(reception, day)
    assert board["view"] == "day"
    assert board["from_day"] == board["to_day"] == day
    by_id = {item["id"]: item for item in board["items"]}
    assert set(by_id) == {first["id"], second["id"]}
    assert by_id[first["id"]]["patient_name"]
    assert by_id[first["id"]]["doctor_name"] == "BS. Mai (mẫu)"
    assert by_id[second["id"]]["status"] == "cancelled"
    assert [d["name"] for d in board["doctors"]][:2] == ["BS. An (mẫu)", "BS. Mai (mẫu)"]
    assert [i["starts_at"] for i in board["items"]] == sorted(i["starts_at"] for i in board["items"])


async def test_the_day_view_filters_by_doctor_and_the_week_view_spans_seven_days(
    client_factory: ClientFactory, world: SeedResult
) -> None:
    reception = await client_factory("reception.lan")
    start = datetime.fromisoformat(fresh_start(10))
    mai = await _book(reception, _body(world, "P027", "doctor.mai", start.isoformat()))
    an = await _book(reception, _body(world, "P029", "doctor.an", (start + timedelta(days=3)).isoformat()))
    far = await _book(reception, _body(world, "P031", "doctor.mai", (start + timedelta(days=7)).isoformat()))
    day = start.date().isoformat()
    only_mai = await _schedule(reception, day, view="week", doctor_id=str(world.users["doctor.mai"]))
    assert [i["id"] for i in only_mai["items"]] == [mai["id"]]
    week = await _schedule(reception, day, view="week")
    assert week["to_day"] == (start.date() + timedelta(days=6)).isoformat()
    assert {i["id"] for i in week["items"]} == {mai["id"], an["id"]}
    assert far["id"] not in {i["id"] for i in week["items"]}


async def test_a_doctor_sees_only_their_own_board_whatever_filter_they_send(
    client_factory: ClientFactory, world: SeedResult
) -> None:
    """filtered(): the signed-in doctor is forced as the doctor filter; no colleague's patient is named."""
    reception = await client_factory("reception.lan")
    mai = await client_factory("doctor.mai")
    start = fresh_start(9)
    mine = await _book(reception, _body(world, "P029", "doctor.mai", start))
    theirs = await _book(reception, _body(world, "P027", "doctor.an", _same_day(start, 10)))
    board = await _schedule(mai, start[:10], doctor_id=str(world.users["doctor.an"]))
    ids = {i["id"] for i in board["items"]}
    assert mine["id"] in ids
    assert theirs["id"] not in ids
    assert board["doctor_id"] == str(world.users["doctor.mai"])
    assert [d["name"] for d in board["doctors"]] == ["BS. Mai (mẫu)"]


async def test_the_board_needs_appointment_read_and_a_naive_day_is_a_422(
    client_factory: ClientFactory, world: SeedResult
) -> None:
    reception = await client_factory("reception.lan")
    assert (
        await reception.get("/api/v1/appointments/schedule", params={"day": "20-09-2026"})
    ).status_code == 422
    assert (await reception.get("/api/v1/appointments/schedule")).status_code == 422


# ------------------------------------------------------------------------------------------ free slot


async def test_the_free_slot_skips_what_the_doctor_and_the_patient_already_have(
    client_factory: ClientFactory, world: SeedResult
) -> None:
    """suggest: first accepted start in steps of 15 minutes from 08:00."""
    reception = await client_factory("reception.lan")
    start = fresh_start(8)
    day = start[:10]
    await _book(reception, _body(world, "P027", "doctor.mai", start, 30))
    params = {
        "patient_id": str(world.patients["P029"]),
        "doctor_id": str(world.users["doctor.mai"]),
        "day": day,
    }
    first = await reception.get("/api/v1/appointments/free-slot", params={**params, "duration_min": 30})
    assert first.status_code == 200, first.text
    assert first.json()["starts_at"] == f"{day}T08:30:00+07:00"
    # the same patient is busy at 08:00 with another doctor: the patient rule skips it as well
    other = await reception.get(
        "/api/v1/appointments/free-slot",
        params={
            "patient_id": str(world.patients["P027"]),
            "doctor_id": str(world.users["doctor.an"]),
            "day": day,
        },
    )
    assert other.json()["starts_at"] == f"{day}T08:30:00+07:00"


async def test_the_free_slot_steps_over_the_lunch_break_and_is_null_when_nothing_fits(
    client_factory: ClientFactory, world: SeedResult
) -> None:
    reception = await client_factory("reception.lan")
    day = fresh_start(8)[:10]
    params = {
        "patient_id": str(world.patients["P029"]),
        "doctor_id": str(world.users["doctor.mai"]),
        "day": day,
    }
    # 4 h from 08:00 would touch the break: 3 h 15 min fits before it, 5 h only after it (13:00-18:00)
    after_break = await reception.get(
        "/api/v1/appointments/free-slot", params={**params, "duration_min": 300}
    )
    assert after_break.json()["starts_at"] == f"{day}T13:00:00+07:00"
    none = await reception.get("/api/v1/appointments/free-slot", params={**params, "duration_min": 360})
    assert none.json() == {"starts_at": None}


async def test_a_doctor_looks_for_a_slot_in_their_own_calendar_only(
    client_factory: ClientFactory, world: SeedResult
) -> None:
    mai = await client_factory("doctor.mai")
    day = fresh_start(8)[:10]
    params = {"patient_id": str(world.patients["P029"]), "day": day}
    own = await mai.get("/api/v1/appointments/free-slot", params=params)
    assert own.status_code == 200, own.text
    assert own.json()["starts_at"] == f"{day}T08:00:00+07:00"
    other = await mai.get(
        "/api/v1/appointments/free-slot", params={**params, "doctor_id": str(world.users["doctor.an"])}
    )
    assert other.status_code == 403


async def test_the_free_slot_refuses_a_stranger_doctor_and_an_unknown_patient(
    client_factory: ClientFactory, world: SeedResult
) -> None:
    reception = await client_factory("reception.lan")
    day = fresh_start(8)[:10]
    not_a_doctor = await reception.get(
        "/api/v1/appointments/free-slot",
        params={
            "patient_id": str(world.patients["P029"]),
            "doctor_id": str(world.users["cs.thu"]),
            "day": day,
        },
    )
    assert not_a_doctor.status_code == 422
    unknown = await reception.get(
        "/api/v1/appointments/free-slot",
        params={"patient_id": "00000000-0000-4000-8000-0000000000aa", "day": day},
    )
    assert unknown.status_code == 404


# ------------------------------------------------------------------------- what a change tells the CRM


async def test_every_change_of_an_appointment_is_announced_without_personal_data(
    client_factory: ClientFactory, world: SeedResult, seen_changes: list[AppointmentChange]
) -> None:
    reception = await client_factory("reception.lan")
    appt = await _book(reception, _body(world, "P027", "doctor.mai", fresh_start()))
    base = f"/api/v1/appointments/{appt['id']}"
    await reception.patch(base, json={"version": 1, "note": "đổi ghi chú"})
    await reception.post(f"{base}/confirm", json={"version": 2})
    await reception.post(f"{base}/miss", json={"version": 3})
    assert [(c.kind, c.status) for c in seen_changes] == [
        ("create", "booked"),
        ("update", "booked"),
        ("confirm", "confirmed"),
        ("miss", "missed"),
    ]
    assert {c.patient_id for c in seen_changes} == {world.patients["P027"]}
    assert all(set(vars_of(c)) == {"appointment_id", "patient_id", "kind", "status"} for c in seen_changes)


def vars_of(change: AppointmentChange) -> dict[str, object]:
    return {name: getattr(change, name) for name in change.__slots__}


async def test_a_failing_listener_never_fails_the_appointment_change(
    client_factory: ClientFactory, world: SeedResult
) -> None:
    def broken(_: AppointmentChange) -> None:
        raise RuntimeError("listener down")

    appointment_events.install_listener(broken)
    try:
        reception = await client_factory("reception.lan")
        appt = await _book(reception, _body(world, "P027", "doctor.mai", fresh_start()))
        assert (
            await reception.post(f"/api/v1/appointments/{appt['id']}/confirm", json={"version": 1})
        ).status_code == 200
    finally:
        appointment_events.install_listener(None)


async def _rule_tasks(admin: Engine, patient_id: UUID, rule: str) -> list[tuple[str, str | None]]:
    with admin.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT status, related_appointment_id::text FROM clinic.crm_task "
                "WHERE patient_id = :p AND rule_key = :r ORDER BY created_at"
            ),
            {"p": patient_id, "r": rule},
        )
        return [(row[0], row[1]) for row in rows]


@pytest.mark.parametrize("how", ["miss", "cancel"])
async def test_a_missed_or_cancelled_visit_makes_the_no_show_rule_open_a_recall_task(
    client_factory: ClientFactory, world: SeedResult, db: ClinicDatabase, admin: Engine, how: str
) -> None:
    """Vắng/hủy chưa đặt lại: the rules read the appointment table, so the status change is the event."""
    reception = await client_factory("reception.lan")
    start = datetime.fromisoformat(fresh_start(9))
    appt = await _book(reception, _body(world, "P032", "doctor.mai", start.isoformat()))
    runner = CrmRulesRunner(SqlCrmRuleStore(db), FakeScheduler())
    later = start + timedelta(days=3)
    await runner.run_clinic(world.clinic_id, now=later)
    assert await _rule_tasks(admin, world.patients["P032"], "no_show") == []
    body = {"version": 1, **({"reason": "bận việc"} if how == "cancel" else {})}
    assert (await reception.post(f"/api/v1/appointments/{appt['id']}/{how}", json=body)).status_code == 200
    await runner.run_clinic(world.clinic_id, now=later)
    assert await _rule_tasks(admin, world.patients["P032"], "no_show") == [("open", appt["id"])]
    # a second run adds nothing
    await runner.run_clinic(world.clinic_id, now=later)
    assert len(await _rule_tasks(admin, world.patients["P032"], "no_show")) == 1


# ---------------------------------------------------------------------------------------- dashboard


def test_the_week_runs_monday_to_sunday_and_the_month_to_its_last_day() -> None:
    assert range_days(DashboardRange.TODAY, DEMO_DAY) == (DEMO_DAY, DEMO_DAY)
    assert range_days(DashboardRange.WEEK, DEMO_DAY) == (date(2026, 9, 14), date(2026, 9, 20))
    assert range_days(DashboardRange.WEEK, date(2026, 9, 21)) == (date(2026, 9, 21), date(2026, 9, 27))
    assert range_days(DashboardRange.MONTH, DEMO_DAY) == (date(2026, 9, 1), date(2026, 9, 30))
    assert range_days(DashboardRange.MONTH, date(2028, 2, 10)) == (date(2028, 2, 1), date(2028, 2, 29))
    assert range_days(DashboardRange.MONTH, date(2026, 12, 31)) == (date(2026, 12, 1), date(2026, 12, 31))


def test_a_percentage_rounds_half_up_and_is_none_without_a_denominator() -> None:
    assert percent(1, 2) == 50
    assert percent(1, 3) == 33
    assert percent(2, 3) == 67
    assert percent(1, 8) == 13
    assert percent(0, 5) == 0
    assert percent(0, 0) is None


async def _kpis(client: httpx.AsyncClient, range_: str = "today") -> dict[str, Any]:
    response = await client.get("/api/v1/dashboard/kpis", params={"range": range_})
    assert response.status_code == 200, response.text
    return response.json()


async def test_the_owner_dashboard_counts_the_demo_data_by_range_and_has_no_money(
    client_factory: ClientFactory, world: SeedResult
) -> None:
    """Demo data: today one confirmed visit (P026), two days ago one missed (P028), +10 days one booked."""
    owner = await client_factory("owner")
    today = await _kpis(owner)
    assert today["scope"] == "clinic"
    assert (today["starts_on"], today["ends_on"]) == ("2026-09-20", "2026-09-20")
    assert today["appointments"] == {
        "total": 1, "upcoming": 1, "waiting": 0, "in_progress": 0,
        "completed": 0, "missed": 0, "cancelled": 0, "visits": 0,
    }  # fmt: skip
    assert today["patients"] == {"seen": 0, "new": 0, "returning": 0}
    week = await _kpis(owner, "week")
    assert (week["starts_on"], week["ends_on"]) == ("2026-09-14", "2026-09-20")
    assert week["appointments"]["total"] == 2
    assert week["appointments"]["missed"] == 1
    month = await _kpis(owner, "month")
    assert month["appointments"]["total"] == 3
    assert month["appointments"]["upcoming"] == 2
    assert "revenue" not in today
    assert not any("revenue" in key or "amount" in key for key in today["appointments"])


async def test_a_check_in_shows_up_in_visits_waiting_and_patients_seen(
    client_factory: ClientFactory, world: SeedResult, admin: Engine
) -> None:
    reception = await client_factory("reception.lan")
    owner = await client_factory("owner")
    today = (
        await reception.get("/api/v1/appointments", params={"patient_id": str(world.patients["P026"])})
    ).json()
    appt = next(a for a in today["items"] if a["starts_at"].startswith("2026-09-20"))
    assert (
        await reception.post(f"/api/v1/appointments/{appt['id']}/check-in", json={"version": appt["version"]})
    ).status_code == 200
    kpis = await _kpis(owner)
    assert kpis["appointments"]["waiting"] == 1
    assert kpis["appointments"]["visits"] == 1
    assert kpis["appointments"]["upcoming"] == 0
    assert kpis["patients"]["seen"] == 1
    assert kpis["patients"]["new"] + kpis["patients"]["returning"] == 1
    with admin.connect() as conn:
        first_contact = conn.execute(
            text("SELECT first_contact_at FROM clinic.patient WHERE id = :p"), {"p": world.patients["P026"]}
        ).scalar_one()
    expected_new = 1 if first_contact is not None and first_contact == DEMO_DAY else 0
    assert kpis["patients"]["new"] == expected_new


async def test_care_numbers_come_from_the_task_and_activity_rows(
    client_factory: ClientFactory, world: SeedResult, admin: Engine
) -> None:
    owner = await client_factory("owner")
    stamp = datetime(2026, 9, 20, 10, 0, tzinfo=VN_TZ)
    with admin.begin() as conn:
        for outcome, channel in (
            ("unanswered", "call"),
            ("callback", "call"),
            ("booked", "zalo"),
            (None, "internal_note"),
        ):
            conn.execute(
                text(
                    "INSERT INTO clinic.crm_activity (clinic_id, patient_id, channel, outcome, note, occurred_at, "
                    "related_appointment_id) VALUES (:c, :p, :ch, :o, 'ghi chú mẫu', :t, :a)"
                ),
                {
                    "c": world.clinic_id,
                    "p": world.patients["P027"],
                    "ch": channel,
                    "o": outcome,
                    "t": stamp,
                    "a": None,
                },
            )
        due_today = conn.execute(
            text(
                "SELECT count(*), count(*) FILTER (WHERE status = 'resolved') FROM clinic.crm_task "
                "WHERE status IN ('open', 'rescheduled', 'resolved') AND due_at >= '2026-09-20 00:00+07' "
                "AND due_at < '2026-09-21 00:00+07'"
            )
        ).one()
        overdue = conn.execute(
            text(
                "SELECT count(*), count(DISTINCT patient_id) FROM clinic.crm_task "
                "WHERE status IN ('open', 'rescheduled') AND due_at < '2026-09-20 00:00+07'"
            )
        ).one()
    care = (await _kpis(owner))["care"]
    assert (care["tasks_due"], care["tasks_resolved"]) == (due_today[0], due_today[1])
    assert (care["overdue_tasks"], care["overdue_patients"]) == (overdue[0], overdue[1])
    assert care["contact_attempts"] == 3  # the internal note is not a contact
    assert care["contacts_reached"] == 2  # unanswered is not
    assert care["contact_rate_pct"] == 67
    assert care["booked_after_care"] == 0
    expected_completion = None if due_today[0] == 0 else round(due_today[1] * 100 / due_today[0])
    assert care["followup_completion_pct"] == expected_completion


async def test_each_role_gets_only_the_blocks_it_may_read(
    client_factory: ClientFactory, world: SeedResult
) -> None:
    reception = await client_factory("reception.lan")
    cs = await client_factory("cs.maianh")
    an = await client_factory("doctor.an")
    mai = await client_factory("doctor.mai")
    desk = await _kpis(reception)
    assert desk["appointments"] is not None
    assert desk["care"] is None
    care_desk = await _kpis(cs)
    assert care_desk["appointments"] is not None
    assert care_desk["care"] is not None
    # a doctor: own appointments only (doctor.an has today's visit, doctor.mai none) and the doctor scope
    assert (await _kpis(an))["scope"] == "doctor"
    assert (await _kpis(an))["appointments"]["total"] == 1
    assert (await _kpis(mai))["appointments"]["total"] == 0
    assert (await _kpis(an, "week"))["appointments"]["total"] == 2


async def test_the_dashboard_refuses_an_unknown_range(
    client_factory: ClientFactory, world: SeedResult
) -> None:
    owner = await client_factory("owner")
    assert (await owner.get("/api/v1/dashboard/kpis", params={"range": "year"})).status_code == 422
