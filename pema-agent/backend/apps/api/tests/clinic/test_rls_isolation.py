# ruff: noqa: S608
"""Row level security isolates clinics, at the database and through the API (two seeded clinics)."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import CursorResult, Engine
from sqlalchemy.exc import DBAPIError

from pema.api.clinic_testing import ClientFactory, fresh_start
from pema.clinic.actions import ClinicAgentFacingActions
from pema.clinic.actions.seed_demo import SeedResult
from pema.core.db import ClinicDatabase
from pema_contracts.actions import ActionContext
from pema_contracts.roles import ActorType

pytestmark = pytest.mark.db

TABLES = (
    "user_account",
    "patient",
    "episode",
    "treatment_plan",
    "treatment_session",
    "appointment",
    "crm_task",
    "crm_activity",
    "channel_identity",
    "conversation",
    "message",
    "review_item",
    "consent",
    "message_template",
    "audit_log",
    "auth_session",
)


def _count(admin: Engine, table: str, clinic_id: object) -> int:
    with admin.connect() as conn:
        return conn.execute(
            text(f"SELECT count(*) FROM clinic.{table} WHERE clinic_id = :c"), {"c": clinic_id}
        ).scalar_one()


async def test_a_session_of_one_clinic_sees_exactly_its_own_rows_in_every_table(
    db: ClinicDatabase, world_a: SeedResult, world_b: SeedResult, admin: Engine
) -> None:
    for table in TABLES:
        for world in (world_a, world_b):
            async with db.session(world.clinic_id) as session:
                visible = await session.scalar(text(f"SELECT count(*) FROM clinic.{table}"))
            assert visible == _count(admin, table, world.clinic_id), table


async def test_without_a_clinic_context_no_row_is_visible(db: ClinicDatabase, world_a: SeedResult) -> None:
    async with db.system_session() as session:
        for table in TABLES:
            assert await session.scalar(text(f"SELECT count(*) FROM clinic.{table}")) == 0, table


async def test_a_row_of_another_clinic_cannot_be_written_or_changed(
    db: ClinicDatabase, world_a: SeedResult, world_b: SeedResult, admin: Engine
) -> None:
    with pytest.raises(DBAPIError):
        async with db.session(world_a.clinic_id) as session:
            await session.execute(
                text("INSERT INTO clinic.patient (clinic_id, code, full_name) VALUES (:c, 'X1', 'x')"),
                {"c": world_b.clinic_id},
            )
    async with db.session(world_a.clinic_id) as session:
        updated = await session.execute(
            text("UPDATE clinic.patient SET full_name = 'hijacked' WHERE clinic_id = :c"),
            {"c": world_b.clinic_id},
        )
        assert isinstance(updated, CursorResult)
        assert updated.rowcount == 0
        deleted = await session.execute(
            text("DELETE FROM clinic.patient WHERE clinic_id = :c"), {"c": world_b.clinic_id}
        )
        assert isinstance(deleted, CursorResult)
        assert deleted.rowcount == 0
    with admin.connect() as conn:
        assert (
            conn.execute(
                text("SELECT count(*) FROM clinic.patient WHERE full_name = 'hijacked'")
            ).scalar_one()
            == 0
        )


async def test_the_worker_role_sees_only_the_views_of_its_own_clinic(
    worker_db: ClinicDatabase, world_a: SeedResult, world_b: SeedResult, admin: Engine
) -> None:
    for world in (world_a, world_b):
        async with worker_db.session(world.clinic_id) as session:
            seen = await session.scalar(text("SELECT count(*) FROM clinic_agent.patient_ref"))
        assert seen == _count(admin, "patient", world.clinic_id)
    async with worker_db.system_session() as session:
        assert await session.scalar(text("SELECT count(*) FROM clinic_agent.patient_ref")) == 0


async def test_the_agent_door_of_one_clinic_does_not_know_a_patient_of_another(
    worker_db: ClinicDatabase, world_a: SeedResult, world_b: SeedResult, admin: Engine
) -> None:
    code = f"B{uuid4().hex[:5]}"
    with admin.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO clinic.patient (clinic_id, code, full_name) VALUES (:c, :code, 'Chỉ ở phòng khám B (mẫu)')"
            ),
            {"c": world_b.clinic_id, "code": code},
        )
    door = ClinicAgentFacingActions(worker_db)
    in_a = ActionContext(clinic_id=world_a.clinic_id, actor_type=ActorType.AGENT)
    in_b = ActionContext(clinic_id=world_b.clinic_id, actor_type=ActorType.AGENT)
    assert await door.get_care_context(in_a, code) is None
    assert (await door.get_care_context(in_b, code)) is not None


async def test_ids_of_another_clinic_answer_404_through_the_api(
    client_factory: ClientFactory, world_a: SeedResult, world_b: SeedResult
) -> None:
    owner_b = await client_factory("clinic-b", "owner")
    foreign_patient = world_a.patients["P025"]
    for path in (
        f"/patients/{foreign_patient}",
        f"/patients/{foreign_patient}/360",
        f"/patients/{foreign_patient}/consents",
        f"/conversations/{world_a.conversation_id}",
        f"/conversations/{world_a.conversation_id}/messages",
    ):
        response = await owner_b.get(f"/api/v1{path}")
        assert response.status_code == 404, path
        assert response.json()["error"]["code"] == "not_found"
    review_a = "00000000-0000-4000-8000-0000000000aa"
    assert (
        await owner_b.post(f"/api/v1/review-items/{review_a}/approve", json={"version": 1})
    ).status_code == 404


async def test_a_listing_never_mixes_clinics_and_cross_clinic_references_are_refused(
    client_factory: ClientFactory, world_a: SeedResult, world_b: SeedResult
) -> None:
    owner_b = await client_factory("clinic-b", "owner")
    page = (await owner_b.get("/api/v1/patients", params={"limit": 200})).json()
    ids = {p["id"] for p in page["items"]}
    assert {str(i) for i in world_b.patients.values()} <= ids
    assert not ids & {str(i) for i in world_a.patients.values()}
    # booking a patient of clinic A from clinic B
    booked = await owner_b.post(
        "/api/v1/appointments",
        json={
            "patient_id": str(world_a.patients["P025"]),
            "doctor_id": str(world_b.users["doctor.mai"]),
            "starts_at": fresh_start(),
        },
    )
    assert booked.status_code == 404
    # assigning a doctor of clinic A to a patient of clinic B
    created = await owner_b.post(
        "/api/v1/patients",
        json={"full_name": "Chéo phòng khám (mẫu)", "doctor_id": str(world_a.users["doctor.mai"])},
    )
    assert created.status_code == 422
    audit_b = (await owner_b.get("/api/v1/admin/logs/audit", params={"limit": 200})).json()
    assert audit_b["items"], "clinic B has its own audit rows"
    users_in_b = {str(i) for i in world_b.users.values()}
    assert all(row["actor_user_id"] in users_in_b | {None} for row in audit_b["items"])


async def test_a_session_cookie_of_clinic_a_is_useless_for_the_data_of_clinic_b(
    client_factory: ClientFactory, world_a: SeedResult, world_b: SeedResult
) -> None:
    owner_a = await client_factory("clinic-a", "owner")
    page = (await owner_a.get("/api/v1/patients", params={"limit": 200})).json()
    assert {p["id"] for p in page["items"]} >= {str(i) for i in world_a.patients.values()}
    assert not {p["id"] for p in page["items"]} & {str(i) for i in world_b.patients.values()}
    assert (await owner_a.get(f"/api/v1/patients/{world_b.patients['P025']}")).status_code == 404
