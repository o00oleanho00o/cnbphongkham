# ruff: noqa: PT018
# new tests (package U, step U4)
"""Service catalog: versioned price and rate terms, the commission terms only for catalog managers, RBAC and
audit. Needs ``PEMA_TEST_DATABASE_URL`` (skipped otherwise)."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError

from pema.api.clinic_testing import ClientFactory
from pema.clinic.actions import services as service_actions
from pema.clinic.actions.seed_demo import SeedResult
from pema.core.db import ClinicDatabase
from pema_contracts.errors import DomainError

pytestmark = pytest.mark.db

SERVICES = "/api/v1/services"


def _new(code: str | None = None, **overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "code": code or f"svc-{uuid4().hex[:8]}",
        "name": "Dịch vụ thử (mẫu)",
        "price_vnd": 800_000,
        "rate_bp": 1500,
        "basis": "net",
        "duration_min": 45,
        "buffer_min": 15,
    }
    body.update(overrides)
    return body


async def test_the_demo_catalog_has_the_four_sample_services_and_the_laser_protocol(
    client_factory: ClientFactory, world: SeedResult
) -> None:
    manager = await client_factory("manager")
    listed = (await manager.get(SERVICES)).json()
    assert {s["code"] for s in listed} == {"follow-up-visit", "dermatology-consult", "laser-co2", "skin-care"}
    laser = next(s for s in listed if s["code"] == "laser-co2")
    assert (laser["price_vnd"], laser["rate_bp"], laser["basis"]) == (2_500_000, 2000, "net")
    assert (laser["duration_min"], laser["buffer_min"], laser["terms_version"]) == (45, 15, 1)
    assert laser["protocol_code"] == "laser-co2"
    assert len(laser["room_ids"]) == 1
    protocols = (await manager.get("/api/v1/protocols")).json()
    assert [p["code"] for p in protocols] == ["laser-co2"]


async def test_a_price_or_rate_change_creates_a_new_version_and_the_old_one_stays_readable(
    client_factory: ClientFactory, world: SeedResult
) -> None:
    manager = await client_factory("manager")
    created = await manager.post(SERVICES, json=_new("peel-light"))
    assert created.status_code == 201, created.text
    service = created.json()
    assert (service["terms_version"], service["version"]) == (1, 1)

    repriced = await manager.patch(
        f"{SERVICES}/{service['id']}", json={"version": service["version"], "price_vnd": 900_000}
    )
    assert repriced.status_code == 200, repriced.text
    assert repriced.json()["terms_version"] == 2
    assert repriced.json()["price_vnd"] == 900_000
    rerated = await manager.patch(
        f"{SERVICES}/{service['id']}",
        json={"version": repriced.json()["version"], "rate_bp": 2000, "basis": "collected"},
    )
    body = rerated.json()
    assert (body["terms_version"], body["rate_bp"], body["basis"]) == (3, 2000, "collected")

    detail = (await manager.get(f"{SERVICES}/{service['id']}")).json()
    assert [h["version_no"] for h in detail["history"]] == [3, 2, 1]
    first = detail["history"][-1]
    assert (first["price_vnd"], first["rate_bp"], first["basis"]) == (800_000, 1500, "net")
    assert detail["history"][0]["changed_by"] == str(world.users["manager"])


async def test_editing_the_name_or_rooms_does_not_create_a_price_version(
    client_factory: ClientFactory, world: SeedResult
) -> None:
    manager = await client_factory("manager")
    service = (await manager.post(SERVICES, json=_new())).json()
    renamed = await manager.patch(
        f"{SERVICES}/{service['id']}", json={"version": 1, "name": "Tên mới (mẫu)", "active": False}
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["terms_version"] == 1
    assert renamed.json()["active"] is False
    assert len((await manager.get(f"{SERVICES}/{service['id']}")).json()["history"]) == 1


async def test_a_change_that_changes_nothing_writes_nothing(
    client_factory: ClientFactory, world: SeedResult, admin: Engine
) -> None:
    manager = await client_factory("manager")
    service = (await manager.post(SERVICES, json=_new())).json()
    same = await manager.patch(
        f"{SERVICES}/{service['id']}", json={"version": 1, "price_vnd": service["price_vnd"]}
    )
    assert same.status_code == 200
    assert same.json()["version"] == 1 and same.json()["terms_version"] == 1
    with admin.connect() as conn:
        updates = conn.execute(
            text("SELECT count(*) FROM clinic.audit_log WHERE action = 'service.update' AND entity_id = :i"),
            {"i": service["id"]},
        ).scalar_one()
    assert updates == 0


async def test_a_stale_version_is_a_409_and_a_duplicate_code_is_a_422(
    client_factory: ClientFactory, world: SeedResult
) -> None:
    manager = await client_factory("manager")
    service = (await manager.post(SERVICES, json=_new("dup-code"))).json()
    ok = await manager.patch(f"{SERVICES}/{service['id']}", json={"version": 1, "price_vnd": 1})
    assert ok.status_code == 200
    stale = await manager.patch(f"{SERVICES}/{service['id']}", json={"version": 1, "price_vnd": 2})
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "version_conflict"
    duplicate = await manager.post(SERVICES, json=_new("dup-code"))
    assert duplicate.status_code == 422
    assert duplicate.json()["error"]["code"] == "validation_failed"


async def test_a_service_can_only_point_at_a_known_protocol_and_known_rooms(
    client_factory: ClientFactory, world: SeedResult
) -> None:
    manager = await client_factory("manager")
    bad_protocol = await manager.post(SERVICES, json=_new(protocol_code="no-such-protocol"))
    assert bad_protocol.status_code == 422
    bad_room = await manager.post(SERVICES, json=_new(room_ids=[str(uuid4())]))
    assert bad_room.status_code == 422
    rooms = (await manager.get("/api/v1/resources")).json()["rooms"]
    ok = await manager.post(
        SERVICES, json=_new(protocol_code="laser-co2", room_ids=[rooms[0]["id"], rooms[1]["id"]])
    )
    assert ok.status_code == 201, ok.text
    assert set(ok.json()["room_ids"]) == {rooms[0]["id"], rooms[1]["id"]}
    detached = await manager.patch(
        f"{SERVICES}/{ok.json()['id']}", json={"version": 1, "protocol_code": None}
    )
    assert detached.json()["protocol_code"] is None


async def test_only_the_owner_and_the_manager_change_the_catalog(
    client_factory: ClientFactory, world: SeedResult
) -> None:
    owner = await client_factory("owner")
    created = (await owner.post(SERVICES, json=_new())).json()
    for key in ("doctor.mai", "cs.maianh", "reception.lan"):
        client = await client_factory(key)
        assert (await client.post(SERVICES, json=_new())).status_code == 403, key
        patch = await client.patch(f"{SERVICES}/{created['id']}", json={"version": 1, "price_vnd": 1})
        assert patch.status_code == 403, key
        assert (
            await client.post("/api/v1/protocols", json={"code": "x-test", "name": "X"})
        ).status_code == 403


async def test_the_commission_terms_are_visible_to_catalog_managers_only(
    client_factory: ClientFactory, world: SeedResult
) -> None:
    manager = await client_factory("manager")
    mine = (await manager.get(SERVICES)).json()
    assert all(s["rate_bp"] is not None and s["basis"] is not None for s in mine)
    for key in ("doctor.mai", "cs.maianh", "reception.lan"):
        client = await client_factory(key)
        listed = await client.get(SERVICES)
        assert listed.status_code == 200, key
        for service in listed.json():
            assert service["rate_bp"] is None and service["basis"] is None
            assert service["price_vnd"] > 0
        detail = (await client.get(f"{SERVICES}/{mine[0]['id']}")).json()
        assert detail["rate_bp"] is None
        assert all(h["rate_bp"] is None and h["basis"] is None for h in detail["history"])


async def test_every_catalog_mutation_leaves_an_audit_row_without_pii(
    client_factory: ClientFactory, world: SeedResult, admin: Engine
) -> None:
    manager = await client_factory("manager")
    created = (await manager.post(SERVICES, json=_new("audited"))).json()
    await manager.patch(
        f"{SERVICES}/{created['id']}", json={"version": 1, "price_vnd": 123_000, "name": "Tên khác (mẫu)"}
    )
    with admin.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT action, details FROM clinic.audit_log WHERE entity_type = 'service' "
                "AND entity_id = :i ORDER BY id"
            ),
            {"i": created["id"]},
        ).all()
    assert [r.action for r in rows] == ["service.create", "service.update"]
    update = rows[1].details
    assert set(update["changed_fields"]) == {"name", "price_vnd"}
    assert update["terms_version"] == 2
    assert "Tên khác" not in str(update)


async def test_a_booking_keeps_the_terms_it_was_made_under(
    client_factory: ClientFactory, world: SeedResult, db: ClinicDatabase
) -> None:
    """``terms_snapshot`` is what orders and finance entries call with the version they stored."""
    manager = await client_factory("manager")
    service = (await manager.post(SERVICES, json=_new())).json()
    await manager.patch(f"{SERVICES}/{service['id']}", json={"version": 1, "price_vnd": 1_000_000})
    async with db.session() as session:
        old = await service_actions.terms_snapshot(session, world.clinic_id, UUID(service["id"]), 1)
        current = await service_actions.terms_snapshot(session, world.clinic_id, UUID(service["id"]))
        assert (old.price_vnd, current.price_vnd, current.version_no) == (800_000, 1_000_000, 2)
        with pytest.raises(DomainError):
            await service_actions.terms_snapshot(session, world.clinic_id, UUID(service["id"]), 9)


async def test_a_snapshot_cannot_be_rewritten_or_deleted_even_by_the_application_role(
    client_factory: ClientFactory, world: SeedResult, db: ClinicDatabase
) -> None:
    manager = await client_factory("manager")
    service = (await manager.post(SERVICES, json=_new())).json()
    async with db.session() as session:
        with pytest.raises(DBAPIError):
            await session.execute(
                text("UPDATE clinic.service_version SET price_vnd = 1 WHERE service_id = :i"),
                {"i": service["id"]},
            )
    async with db.session() as session:
        with pytest.raises(DBAPIError):
            await session.execute(
                text("DELETE FROM clinic.service_version WHERE service_id = :i"), {"i": service["id"]}
            )
