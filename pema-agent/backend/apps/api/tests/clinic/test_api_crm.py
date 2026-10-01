# ruff: noqa: PT018
# ported from: prototype/shared/crm-automation.js (queue, validate, finish) behaviours
"""CRM tasks and the contact log through the HTTP API (the rules that create tasks are package B2's)."""

from __future__ import annotations

from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine

from pema.api.clinic_testing import ClientFactory, fresh_start
from pema.clinic.actions.seed_demo import SeedResult

pytestmark = pytest.mark.db


def new_task(admin: Engine, world: SeedResult, code: str, rule: str, priority: str = "normal") -> str:
    """Insert one open task (the rule engine of B2 creates them in production)."""
    task_id = uuid4()
    with admin.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO clinic.crm_task (id, clinic_id, task_key, patient_id, rule_key, reason, priority, "
                "owner_user_id, due_at, suggested_action) VALUES (:id, :c, :k, :p, :r, 'lý do mẫu', :pr, :o, "
                "'2026-09-20T09:00:00+07:00', 'hành động mẫu')"
            ),
            {
                "id": task_id,
                "c": world.clinic_id,
                "k": f"test:{rule}:{code}:{task_id}",
                "p": world.patients[code],
                "r": rule,
                "pr": priority,
                "o": world.users["cs.maianh"],
            },
        )
    return str(task_id)


def resolve_body(world: SeedResult, **kw: object) -> dict[str, object]:
    body: dict[str, object] = {
        "version": 1,
        "outcome": "no_need",
        "channel": "call",
        "note": "Đã gọi, bệnh nhân chưa có nhu cầu (ghi chú mẫu)",
        "owner_user_id": str(world.users["cs.maianh"]),
    }
    body.update(kw)
    return body


async def _activity_count(client: httpx.AsyncClient, task_id: str) -> int:
    return (await client.get("/api/v1/crm/activities", params={"task_id": task_id})).json()["total"]


async def test_the_queue_puts_d1_d3_d7_first_then_priority_then_due_time(
    client_factory: ClientFactory, world_a: SeedResult, admin: Engine
) -> None:
    """D+1/3/7 đứng đầu, sau đó theo mức ưu tiên và hạn"""
    cs = await client_factory("clinic-a", "cs.maianh")
    patient = world_a.patients["P032"]
    low = new_task(admin, world_a, "P032", "dormant90", "low")
    high = new_task(admin, world_a, "P032", "overdue", "high")
    d3 = new_task(admin, world_a, "P032", "d3", "normal")
    page = (
        await cs.get("/api/v1/crm/tasks", params={"patient_id": str(patient), "task_status": "open"})
    ).json()
    order = [t["id"] for t in page["items"]]
    assert order.index(d3) < order.index(high) < order.index(low)
    assert page["items"][0]["patient_code"] == "P032"


async def test_due_by_filters_the_queue_to_today(
    client_factory: ClientFactory, world_a: SeedResult, admin: Engine
) -> None:
    cs = await client_factory("clinic-a", "cs.maianh")
    later = new_task(admin, world_a, "P032", "birthday")
    with admin.begin() as conn:
        conn.execute(
            text("UPDATE clinic.crm_task SET due_at = '2026-10-05T09:00:00+07:00' WHERE id = :i"),
            {"i": later},
        )
    today = (await cs.get("/api/v1/crm/tasks", params={"due_by": "2026-09-20", "limit": 200})).json()
    assert later not in [t["id"] for t in today["items"]]
    everything = (await cs.get("/api/v1/crm/tasks", params={"limit": 200})).json()
    assert later in [t["id"] for t in everything["items"]]


async def test_unanswered_needs_a_future_next_action_and_reschedules_the_task(
    client_factory: ClientFactory, world_a: SeedResult, admin: Engine
) -> None:
    """Cần ngày giờ gọi lại"""
    cs = await client_factory("clinic-a", "cs.maianh")
    task_id = new_task(admin, world_a, "P032", "d1")
    url = f"/api/v1/crm/tasks/{task_id}/resolve"
    missing = await cs.post(url, json=resolve_body(world_a, outcome="unanswered"))
    assert missing.status_code == 422
    past = await cs.post(
        url, json=resolve_body(world_a, outcome="unanswered", next_action_at="2026-09-20T08:00:00+07:00")
    )
    assert past.status_code == 422
    assert await _activity_count(cs, task_id) == 0, "a refused resolve leaves nothing behind"
    ok = await cs.post(
        url, json=resolve_body(world_a, outcome="unanswered", next_action_at="2026-09-21T10:00:00+07:00")
    )
    assert ok.status_code == 200, ok.text
    task = ok.json()
    assert task["status"] == "rescheduled"
    assert task["due_at"] == "2026-09-21T10:00:00+07:00"
    assert task["resolution"] == "unanswered"
    assert task["resolved_at"] is None
    assert await _activity_count(cs, task_id) == 1


async def test_resolving_records_the_contact_on_the_patient_and_closes_the_task(
    client_factory: ClientFactory, world_a: SeedResult, admin: Engine
) -> None:
    cs = await client_factory("clinic-a", "cs.thu")
    task_id = new_task(admin, world_a, "P032", "d1")
    done = await cs.post(
        f"/api/v1/crm/tasks/{task_id}/resolve",
        json=resolve_body(world_a, owner_user_id=str(world_a.users["cs.thu"]), priority="low"),
    )
    task = done.json()
    assert task["status"] == "resolved"
    assert task["priority"] == "low"
    assert task["owner_name"].startswith("CSKH Thu")
    assert task["resolved_at"] is not None
    patient = (await cs.get(f"/api/v1/patients/{world_a.patients['P032']}")).json()
    assert patient["cs_owner_id"] == str(world_a.users["cs.thu"])
    activities = (await cs.get("/api/v1/crm/activities", params={"task_id": task_id})).json()["items"]
    assert activities[0]["channel"] == "call"
    assert activities[0]["actor_name"].startswith("CSKH Thu")
    # a resolved task cannot be resolved again
    again = await cs.post(f"/api/v1/crm/tasks/{task_id}/resolve", json=resolve_body(world_a, version=2))
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "invalid_state"


async def test_a_retry_with_the_same_idempotency_key_returns_the_first_result_and_logs_once(
    client_factory: ClientFactory, world_a: SeedResult, admin: Engine
) -> None:
    cs = await client_factory("clinic-a", "cs.maianh")
    task_id = new_task(admin, world_a, "P032", "d1")
    url = f"/api/v1/crm/tasks/{task_id}/resolve"
    headers = {"Idempotency-Key": f"resolve-{task_id}"}
    first = await cs.post(url, json=resolve_body(world_a), headers=headers)
    retry = await cs.post(url, json=resolve_body(world_a), headers=headers)
    assert first.status_code == retry.status_code == 200
    assert retry.json()["status"] == "resolved"
    assert await _activity_count(cs, task_id) == 1


async def test_a_stale_version_is_a_409(
    client_factory: ClientFactory, world_a: SeedResult, admin: Engine
) -> None:
    cs = await client_factory("clinic-a", "cs.maianh")
    task_id = new_task(admin, world_a, "P032", "d1")
    response = await cs.post(f"/api/v1/crm/tasks/{task_id}/resolve", json=resolve_body(world_a, version=7))
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "version_conflict"


async def test_booked_saves_the_appointment_the_task_and_the_activity_in_one_transaction(
    client_factory: ClientFactory, world_a: SeedResult, admin: Engine
) -> None:
    """Cần lưu lịch hẹn hợp lệ trước khi hoàn tất việc"""
    cs = await client_factory("clinic-a", "cs.maianh")
    task_id = new_task(admin, world_a, "P031", "dormant90")
    url = f"/api/v1/crm/tasks/{task_id}/resolve"
    no_booking = await cs.post(url, json=resolve_body(world_a, outcome="booked"))
    assert no_booking.status_code == 422
    wrong_patient = await cs.post(
        url,
        json=resolve_body(
            world_a,
            outcome="booked",
            booking={
                "patient_id": str(world_a.patients["P029"]),
                "doctor_id": str(world_a.users["doctor.mai"]),
                "starts_at": fresh_start(),
            },
        ),
    )
    assert wrong_patient.status_code == 422
    booking = {
        "patient_id": str(world_a.patients["P031"]),
        "doctor_id": str(world_a.users["doctor.mai"]),
        "starts_at": fresh_start(9),
    }
    ok = await cs.post(url, json=resolve_body(world_a, outcome="booked", booking=booking))
    assert ok.status_code == 200, ok.text
    task = ok.json()
    assert task["status"] == "resolved"
    assert task["related_appointment_id"]
    activity = (await cs.get("/api/v1/crm/activities", params={"task_id": task_id})).json()["items"][0]
    assert activity["related_appointment_id"] == task["related_appointment_id"]
    reception = await client_factory("clinic-a", "reception.lan")
    appt = (await reception.get(f"/api/v1/appointments/{task['related_appointment_id']}")).json()
    assert appt["patient_code"] == "P031"


async def test_a_booking_conflict_rolls_everything_back_and_the_task_stays_open(
    client_factory: ClientFactory, world_a: SeedResult, admin: Engine
) -> None:
    """lưu save rollback: lịch trùng thì việc vẫn mở, không có activity"""
    cs = await client_factory("clinic-a", "cs.maianh")
    reception = await client_factory("clinic-a", "reception.lan")
    start = fresh_start(9)
    taken = await reception.post(
        "/api/v1/appointments",
        json={
            "patient_id": str(world_a.patients["P029"]),
            "doctor_id": str(world_a.users["doctor.mai"]),
            "starts_at": start,
        },
    )
    assert taken.status_code == 201
    task_id = new_task(admin, world_a, "P031", "dormant90")
    booking = {
        "patient_id": str(world_a.patients["P031"]),
        "doctor_id": str(world_a.users["doctor.mai"]),
        "starts_at": start,
    }
    clash = await cs.post(
        f"/api/v1/crm/tasks/{task_id}/resolve", json=resolve_body(world_a, outcome="booked", booking=booking)
    )
    assert clash.status_code == 409
    assert (await cs.get(f"/api/v1/crm/tasks/{task_id}")).json()["status"] == "open"
    assert await _activity_count(cs, task_id) == 0


async def test_optout_sets_the_marketing_opt_out_flag(
    client_factory: ClientFactory, world_a: SeedResult, admin: Engine
) -> None:
    cs = await client_factory("clinic-a", "cs.maianh")
    task_id = new_task(admin, world_a, "P032", "birthday")
    done = await cs.post(f"/api/v1/crm/tasks/{task_id}/resolve", json=resolve_body(world_a, outcome="optout"))
    assert done.status_code == 200
    assert (await cs.get(f"/api/v1/patients/{world_a.patients['P032']}")).json()["marketing_opt_out"] is True


async def test_a_complaint_is_handed_to_a_doctor_as_a_triage_alert_without_the_note_text(
    client_factory: ClientFactory, world_a: SeedResult, admin: Engine
) -> None:
    cs = await client_factory("clinic-a", "cs.maianh")
    mai = await client_factory("clinic-a", "doctor.mai")
    task_id = new_task(admin, world_a, "P025", "d3")
    note = "Khiếu nại mẫu về buổi điều trị"
    done = await cs.post(
        f"/api/v1/crm/tasks/{task_id}/resolve", json=resolve_body(world_a, outcome="complaint", note=note)
    )
    assert done.status_code == 200
    items = (
        await mai.get(
            "/api/v1/review-items",
            params={"patient_id": str(world_a.patients["P025"]), "kind": "triage_alert"},
        )
    ).json()["items"]
    handed = [i for i in items if i["origin"] == "crm_rule"]
    assert handed and handed[0]["requires_doctor"] is True
    assert note not in str(handed[0])
    # the care member does not even see it
    cs_items = (await cs.get("/api/v1/review-items", params={"kind": "triage_alert"})).json()["items"]
    assert all(i["origin"] != "crm_rule" for i in cs_items)
    activity = (await cs.get("/api/v1/crm/activities", params={"task_id": task_id})).json()["items"][0]
    assert activity["kind"] == "complaint"


async def test_a_doctor_sees_and_resolves_only_d7_reviews_of_their_own_patients(
    client_factory: ClientFactory, world_a: SeedResult, admin: Engine
) -> None:
    """Tài khoản bác sĩ chỉ xử lý review D+7 của hồ sơ phụ trách"""
    mai = await client_factory("clinic-a", "doctor.mai")
    d7_mine = new_task(admin, world_a, "P025", "d7")
    d7_foreign = new_task(admin, world_a, "P030", "d7")
    other_rule = new_task(admin, world_a, "P025", "d1")
    page = (await mai.get("/api/v1/crm/tasks", params={"limit": 200})).json()
    ids = {t["id"] for t in page["items"]}
    assert d7_mine in ids
    assert d7_foreign not in ids and other_rule not in ids
    assert (await mai.get(f"/api/v1/crm/tasks/{other_rule}")).status_code == 404
    body = resolve_body(world_a, owner_user_id=str(world_a.users["doctor.mai"]), channel="internal_note")
    assert (await mai.post(f"/api/v1/crm/tasks/{other_rule}/resolve", json=body)).status_code == 404
    assert (await mai.post(f"/api/v1/crm/tasks/{d7_foreign}/resolve", json=body)).status_code == 404
    done = await mai.post(f"/api/v1/crm/tasks/{d7_mine}/resolve", json=body)
    assert done.status_code == 200, done.text


async def test_reception_has_no_crm_access(client_factory: ClientFactory, world_a: SeedResult) -> None:
    reception = await client_factory("clinic-a", "reception.lan")
    assert (await reception.get("/api/v1/crm/tasks")).status_code == 403
    assert (await reception.get("/api/v1/crm/activities")).status_code == 403


async def test_a_manual_note_does_not_close_a_task_and_internal_notes_do_not_count_as_contact(
    client_factory: ClientFactory, world_a: SeedResult, admin: Engine
) -> None:
    cs = await client_factory("clinic-a", "cs.maianh")
    task_id = new_task(admin, world_a, "P032", "birthday")
    note = await cs.post(
        "/api/v1/crm/activities",
        json={
            "patient_id": str(world_a.patients["P032"]),
            "task_id": task_id,
            "channel": "internal_note",
            "note": "Ghi chú nội bộ mẫu",
        },
    )
    assert note.status_code == 201
    assert note.json()["kind"] == "note"
    assert (await cs.get(f"/api/v1/crm/tasks/{task_id}")).json()["status"] == "open"
    foreign = await cs.post(
        "/api/v1/crm/activities",
        json={
            "patient_id": str(world_a.patients["P029"]),
            "task_id": task_id,
            "channel": "call",
            "note": "sai bệnh nhân",
        },
    )
    assert foreign.status_code == 422
    past = await cs.post(
        "/api/v1/crm/activities",
        json={
            "patient_id": str(world_a.patients["P032"]),
            "channel": "call",
            "note": "x",
            "next_action_at": "2026-09-19T10:00:00+07:00",
        },
    )
    assert past.status_code == 422
