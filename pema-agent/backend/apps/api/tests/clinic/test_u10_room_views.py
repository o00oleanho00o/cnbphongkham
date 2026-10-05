# ported from: prototype/shared/operations-data.js (validate: room blocked, room busy; block: room has an appointment)
"""Package U step U10: the room of an appointment, the room rules of the one validator, the room blocks the
room-column grid shows and the creator name of the reception table. Needs ``PEMA_TEST_DATABASE_URL``."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx
import pytest

from pema.api.clinic_testing import ClientFactory, fresh_start
from pema.clinic.actions.seed_demo import SeedResult

pytestmark = pytest.mark.db


def _at(start: str, hour: int, minute: int = 0) -> str:
    return datetime.fromisoformat(start).replace(hour=hour, minute=minute).isoformat()


def _day(start: str) -> str:
    return start[:10]


def _body(
    world: SeedResult, code: str, doctor: str, start: str, room: str | None, minutes: int = 30
) -> dict[str, object]:
    return {
        "patient_id": str(world.patients[code]),
        "doctor_id": str(world.users[doctor]),
        "room_id": room,
        "starts_at": start,
        "duration_min": minutes,
    }


async def _rooms(client: httpx.AsyncClient) -> list[dict[str, Any]]:
    response = await client.get("/api/v1/resources", params={"day": "2026-09-20"})
    assert response.status_code == 200, response.text
    return response.json()["rooms"]


async def _book(client: httpx.AsyncClient, body: dict[str, object]) -> httpx.Response:
    return await client.post("/api/v1/appointments", json=body)


async def _block(
    client: httpx.AsyncClient, room: str, day: str, start: str, end: str, reason: str
) -> httpx.Response:
    return await client.post(
        "/api/v1/room-blocks",
        json={"room_id": room, "day": day, "start": start, "end": end, "reason": reason},
    )


async def test_a_visit_keeps_its_room_and_the_board_returns_rooms_blocks_and_the_creator(
    client_factory: ClientFactory, world: SeedResult
) -> None:
    reception = await client_factory("reception.lan")
    manager = await client_factory("manager")
    room = (await _rooms(manager))[1]
    start = fresh_start(9)
    created = await _book(reception, _body(world, "P025", "doctor.mai", start, room["id"]))
    assert created.status_code == 201, created.text
    assert created.json()["room_id"] == room["id"]
    assert (await _block(manager, room["id"], _day(start), "14:00", "15:00", "Bảo trì")).status_code == 201

    board = (await reception.get("/api/v1/appointments/schedule", params={"day": _day(start)})).json()
    assert {r["id"] for r in board["rooms"]} >= {room["id"]}
    assert [(b["room_id"], b["start"], b["end"], b["reason"]) for b in board["blocks"]] == [
        (room["id"], "14:00", "15:00", "Bảo trì")
    ]
    row = next(i for i in board["items"] if i["id"] == created.json()["id"])
    assert row["room_id"] == room["id"]
    assert row["room_name"] == room["name"]
    assert row["created_by_name"]  # the reception account that booked it
    elsewhere = (await reception.get("/api/v1/appointments/schedule", params={"day": "2026-01-01"})).json()
    assert elsewhere["blocks"] == []


async def test_a_visit_without_a_room_stays_valid(client_factory: ClientFactory, world: SeedResult) -> None:
    reception = await client_factory("reception.lan")
    created = await _book(reception, _body(world, "P026", "doctor.an", fresh_start(10), None))
    assert created.status_code == 201, created.text
    assert created.json()["room_id"] is None


async def test_a_busy_room_refuses_an_overlap_and_a_cancelled_visit_frees_it(
    client_factory: ClientFactory, world: SeedResult
) -> None:
    """JS validate: ``Phòng đang bận hoặc đang chuẩn bị sau lịch HH:MM.`` (a different doctor and patient)."""
    reception = await client_factory("reception.lan")
    room = (await _rooms(reception))[0]["id"]
    start = fresh_start(9)
    first = await _book(reception, _body(world, "P025", "doctor.mai", start, room, 45))
    assert first.status_code == 201, first.text
    clash = await _book(reception, _body(world, "P026", "doctor.an", _at(start, 9, 30), room))
    assert clash.status_code == 409, clash.text
    error = clash.json()["error"]
    assert error["code"] == "appointment_conflict"
    assert error["message"] == "Phòng đang bận hoặc đang chuẩn bị sau lịch 09:00."
    other_room = (await _rooms(reception))[1]["id"]
    assert (
        await _book(reception, _body(world, "P026", "doctor.an", _at(start, 9, 30), other_room))
    ).status_code == 201
    touching = await _book(reception, _body(world, "P027", "doctor.mai", _at(start, 9, 45), room))
    assert touching.status_code == 201, touching.text

    cancelled = await reception.post(
        f"/api/v1/appointments/{first.json()['id']}/cancel", json={"version": 1, "reason": "Khách hoãn"}
    )
    assert cancelled.status_code == 200, cancelled.text
    again = await _book(reception, _body(world, "P028", "doctor.mai", start, room))
    assert again.status_code == 201, again.text


async def test_a_blocked_room_refuses_a_booking_in_the_window_only(
    client_factory: ClientFactory, world: SeedResult
) -> None:
    """JS validate: ``Trùng thời gian khóa: <lý do>``; a visit that ends when the block starts is fine."""
    reception = await client_factory("reception.lan")
    manager = await client_factory("manager")
    room = (await _rooms(manager))[2]["id"]
    start = fresh_start(9)
    assert (await _block(manager, room, _day(start), "14:00", "15:00", "Bảo trì thiết bị")).status_code == 201
    inside = await _book(reception, _body(world, "P025", "doctor.mai", _at(start, 14, 30), room))
    assert inside.status_code == 409, inside.text
    assert inside.json()["error"]["message"] == "Trùng thời gian khóa: Bảo trì thiết bị"
    straddle = await _book(reception, _body(world, "P025", "doctor.mai", _at(start, 13, 45), room))
    assert straddle.status_code == 409
    before = await _book(reception, _body(world, "P025", "doctor.mai", _at(start, 13, 30), room))
    assert before.status_code == 201, before.text
    after = await _book(reception, _body(world, "P026", "doctor.mai", _at(start, 15, 0), room))
    assert after.status_code == 201, after.text


async def test_an_unknown_or_inactive_room_is_refused(
    client_factory: ClientFactory, world: SeedResult
) -> None:
    reception = await client_factory("reception.lan")
    manager = await client_factory("manager")
    room = (await _rooms(manager))[3]
    unknown = await _book(
        reception, _body(world, "P025", "doctor.mai", fresh_start(9), "00000000-0000-4000-8000-000000000000")
    )
    assert unknown.status_code == 422, unknown.text
    off = await manager.patch(
        f"/api/v1/rooms/{room['id']}", json={"version": room["version"], "active": False}
    )
    assert off.status_code == 200, off.text
    inactive = await _book(reception, _body(world, "P025", "doctor.mai", fresh_start(9), room["id"]))
    assert inactive.status_code == 422, inactive.text
    assert inactive.json()["error"]["message"] == "Phòng đang tạm ngưng."
    restore = await manager.patch(
        f"/api/v1/rooms/{room['id']}", json={"version": off.json()["version"], "active": True}
    )
    assert restore.status_code == 200


async def test_moving_a_visit_checks_the_room_and_skips_the_visit_itself(
    client_factory: ClientFactory, world: SeedResult
) -> None:
    reception = await client_factory("reception.lan")
    room = (await _rooms(reception))[0]["id"]
    start = fresh_start(9)
    mine = (await _book(reception, _body(world, "P025", "doctor.mai", start, room, 60))).json()
    other = (await _book(reception, _body(world, "P026", "doctor.an", _at(start, 11, 0), room))).json()
    # the visit overlaps itself when it is moved by 15 minutes: allowed
    moved = await reception.patch(
        f"/api/v1/appointments/{mine['id']}",
        json={"version": mine["version"], "starts_at": _at(start, 9, 15)},
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["room_id"] == room
    # into the other visit's time: refused with the room sentence
    clash = await reception.patch(
        f"/api/v1/appointments/{mine['id']}",
        json={"version": moved.json()["version"], "starts_at": _at(start, 11, 0)},
    )
    assert clash.status_code == 409, clash.text
    assert clash.json()["error"]["message"] == "Phòng đang bận hoặc đang chuẩn bị sau lịch 11:00."
    # taking the room off the other visit, then the first may take that time
    free = await reception.patch(
        f"/api/v1/appointments/{other['id']}", json={"version": other["version"], "room_id": None}
    )
    assert free.status_code == 200, free.text
    assert free.json()["room_id"] is None
    ok = await reception.patch(
        f"/api/v1/appointments/{mine['id']}",
        json={"version": moved.json()["version"], "starts_at": _at(start, 11, 0)},
    )
    assert ok.status_code == 200, ok.text


async def test_a_room_with_an_active_visit_cannot_be_blocked_in_that_window(
    client_factory: ClientFactory, world: SeedResult
) -> None:
    """JS block: ``Có lịch hẹn trong khoảng này. Hãy dời lịch trước khi khóa phòng.``"""
    reception = await client_factory("reception.lan")
    manager = await client_factory("manager")
    room = (await _rooms(manager))[0]["id"]
    start = fresh_start(9)
    visit = (await _book(reception, _body(world, "P025", "doctor.mai", start, room, 45))).json()
    refused = await _block(manager, room, _day(start), "09:30", "10:30", "Vệ sinh")
    assert refused.status_code == 409, refused.text
    assert (
        refused.json()["error"]["message"]
        == "Có lịch hẹn trong khoảng này. Hãy dời lịch trước khi khóa phòng."
    )
    clear = await _block(manager, room, _day(start), "10:00", "11:00", "Vệ sinh")
    assert clear.status_code == 201, clear.text
    cancelled = await reception.post(
        f"/api/v1/appointments/{visit['id']}/cancel", json={"version": 1, "reason": "Khách hoãn"}
    )
    assert cancelled.status_code == 200, cancelled.text
    now_ok = await _block(manager, room, _day(start), "09:30", "10:30", "Vệ sinh sâu")
    assert now_ok.status_code == 201, now_ok.text


async def test_only_catalog_managers_block_a_room_and_the_window_stays_inside_08_to_18(
    client_factory: ClientFactory, world: SeedResult
) -> None:
    reception = await client_factory("reception.lan")
    manager = await client_factory("manager")
    room = (await _rooms(manager))[0]["id"]
    day = _day(fresh_start(9))
    assert (await _block(reception, room, day, "09:00", "10:00", "x")).status_code == 403
    for start, end, reason in (("07:30", "09:00", "x"), ("17:00", "18:30", "x"), ("10:00", "09:00", "x")):
        bad = await _block(manager, room, day, start, end, reason)
        assert bad.status_code == 422, (start, end, bad.text)
