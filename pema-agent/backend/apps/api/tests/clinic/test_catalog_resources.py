# ruff: noqa: PT018
# new tests (package U, step U4)
"""Doctors, rooms and room blocks ("Bác sĩ & phòng"), the protocols endpoints and the photo studio. Needs
``PEMA_TEST_DATABASE_URL`` (skipped otherwise)."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine

from pema.api.clinic_testing import ClientFactory
from pema.clinic.actions.seed_demo import DEMO_DAY, SeedResult

pytestmark = pytest.mark.db

DAY = DEMO_DAY.isoformat()  # 2026-09-20, a Sunday
MONDAY = "2026-09-21"


def _shift_everyday(admin: Engine, world: SeedResult, key: str) -> None:
    interval = [{"start": "08:00", "end": "12:00"}, {"start": "13:00", "end": "18:00"}]
    shift = dict.fromkeys(("mon", "tue", "wed", "thu", "fri", "sat", "sun"), interval)
    with admin.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO clinic.staff_profiles (clinic_id, user_id, role, shift) "
                "VALUES (:c, :u, 'doctor', CAST(:s AS jsonb)) ON CONFLICT (user_id) DO UPDATE SET shift = EXCLUDED.shift"
            ),
            {"c": world.clinic_id, "u": world.users[key], "s": __import__("json").dumps(shift)},
        )


async def test_the_resources_page_lists_doctors_rooms_and_blocks_from_the_day_on(
    client_factory: ClientFactory, world: SeedResult
) -> None:
    reception = await client_factory("reception.lan")
    response = await reception.get("/api/v1/resources", params={"day": DAY})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["day"] == DAY
    assert {d["user_id"] for d in body["doctors"]} == {
        str(world.users["doctor.mai"]),
        str(world.users["doctor.an"]),
    }
    assert [r["name"] for r in body["rooms"]] == [
        "Chăm sóc da",
        "Khám da liễu",
        "Laser & thủ thuật",
        "Tư vấn chuyên sâu",
    ]
    assert [(b["day"], b["start"], b["end"], b["reason"]) for b in body["blocks"]] == [
        ("2026-09-21", "14:00", "15:00", "Bảo trì thiết bị laser")
    ]
    later = (await reception.get("/api/v1/resources", params={"day": "2026-09-22"})).json()
    assert later["blocks"] == []


async def test_a_doctor_card_reads_the_shift_of_care_staff_and_the_load_of_the_day(
    client_factory: ClientFactory, world: SeedResult, admin: Engine
) -> None:
    _shift_everyday(admin, world, "doctor.mai")
    manager = await client_factory("manager")
    doctors = {
        d["user_id"]: d
        for d in (await manager.get("/api/v1/resources", params={"day": DAY})).json()["doctors"]
    }
    mai = doctors[str(world.users["doctor.mai"])]
    assert mai["has_shift"] is True
    assert mai["shift"] == [{"start": "08:00", "end": "12:00"}, {"start": "13:00", "end": "18:00"}]
    assert mai["shift_minutes"] == 540, "the 12:00-13:00 break is the gap between the two intervals"
    an = doctors[str(world.users["doctor.an"])]
    assert an["has_shift"] is False and an["shift"] == [] and an["shift_minutes"] == 0
    assert mai["booked_count"] >= 0
    assert all(d["booked_minutes"] >= 0 for d in doctors.values())


async def test_the_load_counts_active_appointments_of_that_doctor_and_day_only(
    client_factory: ClientFactory, world: SeedResult, admin: Engine
) -> None:
    patient = world.patients["P027"]
    mai = world.users["doctor.mai"]
    with admin.begin() as conn:
        conn.execute(text("DELETE FROM clinic.appointment WHERE doctor_id = :d"), {"d": mai})
        for starts, duration, status in (
            ("2026-10-05 09:00+07", 30, "booked"),
            ("2026-10-05 10:00+07", 45, "arrived"),
            ("2026-10-05 11:00+07", 60, "cancelled"),
            ("2026-10-06 09:00+07", 30, "booked"),
        ):
            conn.execute(
                text(
                    "INSERT INTO clinic.appointment (clinic_id, patient_id, doctor_id, starts_at, duration_min, status) "
                    "VALUES (:c, :p, :d, :s, :m, :st)"
                ),
                {"c": world.clinic_id, "p": patient, "d": mai, "s": starts, "m": duration, "st": status},
            )
    manager = await client_factory("manager")
    body = (await manager.get("/api/v1/resources", params={"day": "2026-10-05"})).json()
    card = next(d for d in body["doctors"] if d["user_id"] == str(mai))
    assert (card["booked_count"], card["booked_minutes"]) == (2, 75)


async def test_a_manager_adds_and_edits_rooms_and_the_name_is_unique(
    client_factory: ClientFactory, world: SeedResult
) -> None:
    manager = await client_factory("manager")
    created = await manager.post("/api/v1/rooms", json={"name": "Phòng thử (mẫu)", "capacity": 2})
    assert created.status_code == 201, created.text
    room = created.json()
    assert (room["capacity"], room["active"], room["version"]) == (2, True, 1)
    duplicate = await manager.post("/api/v1/rooms", json={"name": "Phòng thử (mẫu)"})
    assert duplicate.status_code == 422
    off = await manager.patch(f"/api/v1/rooms/{room['id']}", json={"version": 1, "active": False})
    assert off.status_code == 200 and off.json()["active"] is False
    stale = await manager.patch(f"/api/v1/rooms/{room['id']}", json={"version": 1, "capacity": 3})
    assert stale.status_code == 409
    clash = await manager.patch(f"/api/v1/rooms/{room['id']}", json={"version": 2, "name": "Khám da liễu"})
    assert clash.status_code == 422


async def _a_room(client: Any) -> dict[str, Any]:
    return (await client.get("/api/v1/resources", params={"day": DAY})).json()["rooms"][0]


async def test_a_room_block_stays_inside_08_to_18_with_a_reason_and_can_be_removed(
    client_factory: ClientFactory, world: SeedResult, admin: Engine
) -> None:
    manager = await client_factory("manager")
    room = await _a_room(manager)
    base = {"room_id": room["id"], "day": MONDAY, "start": "09:00", "end": "10:00", "reason": "Vệ sinh phòng"}
    ok = await manager.post("/api/v1/room-blocks", json=base)
    assert ok.status_code == 201, ok.text
    for patch in (
        {"start": "07:30"},
        {"end": "18:30"},
        {"start": "10:00", "end": "09:00"},
        {"start": "09:00", "end": "09:00"},
        {"reason": "  "},
        {"room_id": str(uuid4())},
    ):
        bad = await manager.post("/api/v1/room-blocks", json={**base, **patch})
        assert bad.status_code in (404, 422), patch
    listed = (await manager.get("/api/v1/resources", params={"day": MONDAY})).json()["blocks"]
    assert ok.json()["id"] in {b["id"] for b in listed}
    gone = await manager.delete(f"/api/v1/room-blocks/{ok.json()['id']}")
    assert gone.status_code == 204
    assert (await manager.delete(f"/api/v1/room-blocks/{ok.json()['id']}")).status_code == 404
    with admin.connect() as conn:
        actions = (
            conn.execute(
                text(
                    "SELECT action FROM clinic.audit_log WHERE entity_type = 'room_block' AND entity_id = :i ORDER BY id"
                ),
                {"i": ok.json()["id"]},
            )
            .scalars()
            .all()
        )
    assert actions == ["room_block.create", "room_block.delete"]


async def test_resources_are_read_by_the_schedule_roles_and_changed_by_catalog_managers_only(
    client_factory: ClientFactory, world: SeedResult
) -> None:
    for key in ("doctor.mai", "cs.maianh", "reception.lan"):
        client = await client_factory(key)
        assert (await client.get("/api/v1/resources")).status_code == 200, key
        assert (await client.post("/api/v1/rooms", json={"name": f"Phòng {key}"})).status_code == 403, key
        block = {"room_id": str(uuid4()), "day": MONDAY, "start": "09:00", "end": "10:00", "reason": "x"}
        assert (await client.post("/api/v1/room-blocks", json=block)).status_code == 403, key
        assert (await client.delete(f"/api/v1/room-blocks/{uuid4()}")).status_code == 403, key


async def test_protocol_milestones_are_validated_and_edited_with_the_version(
    client_factory: ClientFactory, world: SeedResult
) -> None:
    manager = await client_factory("manager")
    laser = next(p for p in (await manager.get("/api/v1/protocols")).json() if p["code"] == "laser-co2")
    assert [(m["rule_key"], m["day"]) for m in laser["milestones"]] == [("d1", 1), ("d3", 3), ("d7", 7)]
    assert (laser["followup_days"], laser["window_days"]) == (30, 45)
    url = f"/api/v1/protocols/{laser['id']}"
    for bad in (
        [{"rule_key": "due", "day": 1}],
        [{"rule_key": "d1", "day": 1}, {"rule_key": "d1", "day": 2}],
        [{"rule_key": "d7", "day": 60}],
    ):
        refused = await manager.patch(url, json={"version": laser["version"], "milestones": bad})
        assert refused.status_code == 422, bad
    ok = await manager.patch(
        url,
        json={
            "version": laser["version"],
            "milestones": [
                {"rule_key": "d1", "day": 2},
                {"rule_key": "d3", "day": 4},
                {"rule_key": "d7", "day": 8},
            ],
            "followup_days": 21,
        },
    )
    assert ok.status_code == 200, ok.text
    assert [m["day"] for m in ok.json()["milestones"]] == [2, 4, 8]
    assert ok.json()["followup_days"] == 21
    cleared = await manager.patch(url, json={"version": ok.json()["version"], "followup_days": None})
    assert cleared.json()["followup_days"] is None
    stale = await manager.patch(url, json={"version": laser["version"], "active": False})
    assert stale.status_code == 409


async def test_a_new_protocol_needs_a_unique_code_and_is_read_by_the_doctor_who_records_sessions(
    client_factory: ClientFactory, world: SeedResult
) -> None:
    manager = await client_factory("manager")
    body = {
        "code": "peel-5",
        "name": "Peel (mẫu)",
        "followup_days": 14,
        "milestones": [{"rule_key": "d1", "day": 1}],
    }
    created = await manager.post("/api/v1/protocols", json=body)
    assert created.status_code == 201, created.text
    assert (await manager.post("/api/v1/protocols", json=body)).status_code == 422
    mai = await client_factory("doctor.mai")
    assert {p["code"] for p in (await mai.get("/api/v1/protocols")).json()} == {"laser-co2", "peel-5"}
    assert (
        await mai.patch(f"/api/v1/protocols/{created.json()['id']}", json={"version": 1, "active": False})
    ).status_code == 403
    reception = await client_factory("reception.lan")
    assert (await reception.get("/api/v1/protocols")).status_code == 403


async def test_the_studio_is_for_those_who_open_the_patient_and_records_the_read(
    client_factory: ClientFactory, world: SeedResult, admin: Engine
) -> None:
    patient = world.patients["P025"]
    cs = await client_factory("cs.maianh")
    response = await cs.get(f"/api/v1/studio/{patient}")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["patient_id"] == str(patient)
    assert body["views"] == ["Chính diện", "Má trái", "Má phải"] and body["view"] == "Chính diện"
    assert body["photos"] == [] and isinstance(body["media_consent"], bool)
    assert (await cs.get(f"/api/v1/studio/{patient}", params={"view": "Má trái"})).json()["view"] == "Má trái"
    assert (await cs.get(f"/api/v1/studio/{patient}", params={"view": "Sau gáy"})).status_code == 422
    assert (await cs.get(f"/api/v1/studio/{uuid4()}")).status_code == 404
    reception = await client_factory("reception.lan")
    assert (await reception.get(f"/api/v1/studio/{patient}")).status_code == 403
    with admin.connect() as conn:
        reads = conn.execute(
            text("SELECT count(*) FROM clinic.audit_log WHERE action = 'studio.view' AND entity_id = :i"),
            {"i": str(patient)},
        ).scalar_one()
    assert reads >= 2


async def test_the_studio_reports_the_newest_media_consent(
    client_factory: ClientFactory, world: SeedResult
) -> None:
    patient = world.patients["P026"]
    cs = await client_factory("cs.maianh")
    base = f"/api/v1/patients/{patient}/consents"
    granted = await cs.post(base, json={"kind": "media", "granted": True, "source": "front_desk"})
    assert granted.status_code in (200, 201), granted.text
    assert (await cs.get(f"/api/v1/studio/{patient}")).json()["media_consent"] is True
    revoked = await cs.post(base, json={"kind": "media", "granted": False, "source": "front_desk"})
    assert revoked.status_code in (200, 201), revoked.text
    assert (await cs.get(f"/api/v1/studio/{patient}")).json()["media_consent"] is False
