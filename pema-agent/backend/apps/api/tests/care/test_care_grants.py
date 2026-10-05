"""Who may read and write the package-M tables (step M1). New tests (no zalo-agent original).

Needs ``PEMA_TEST_DATABASE_URL``. ``agent_worker`` writes ``agent.*`` and reads the three staff tables only
through the ``clinic_agent`` views (it keeps NO privilege on schema ``clinic``, see the migration docstring);
``be_app`` owns the writes to the three ``clinic.*`` tables.
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import ProgrammingError

from pema.care.models import (
    ActionLog,
    AgentTask,
    CareAgent,
    CareMemory,
    ConversationControl,
    HandoffRequest,
    OnCallContact,
    PatientOwnership,
    Skill,
    StaffProfile,
)
from pema.care.pairing import ensure_care_agent
from pema.clinic.actions.seed_demo import SeedResult
from pema.core.db import ClinicDatabase

pytestmark = pytest.mark.db

CLINIC_INSERTS = {
    "clinic.staff_profiles": "INSERT INTO clinic.staff_profiles (clinic_id, user_id, role) VALUES (:c, :u, 'cs_staff')",
    "clinic.patient_ownership": "INSERT INTO clinic.patient_ownership (clinic_id, patient_id) VALUES (:c, :p)",
    "clinic.on_call_contacts": "INSERT INTO clinic.on_call_contacts (clinic_id, zalo_number, owner) VALUES (:c, '0000000002', 'x')",
}


def _params(world: SeedResult) -> dict[str, Any]:
    return {"c": world.clinic_id, "u": world.users["cs.thu"], "p": world.patients["P025"]}


async def _seed_clinic_rows(db: ClinicDatabase, world: SeedResult) -> None:
    async with db.session() as session:
        session.add(
            StaffProfile(
                clinic_id=world.clinic_id, user_id=world.users["cs.thu"], role="cs_staff", skills=["laser"]
            )
        )
        session.add(
            PatientOwnership(
                clinic_id=world.clinic_id,
                patient_id=world.patients["P025"],
                cs_owner=world.users["cs.thu"],
                doctor=world.users["doctor.mai"],
            )
        )
        session.add(
            OnCallContact(
                clinic_id=world.clinic_id, zalo_number="0000000003", owner="Trực (mẫu)", is_fixture=True
            )
        )


async def test_the_worker_cannot_insert_into_clinic_tables(
    worker_db: ClinicDatabase, world: SeedResult
) -> None:
    for table, sql in CLINIC_INSERTS.items():
        with pytest.raises(ProgrammingError, match="permission denied"):
            async with worker_db.session() as session:
                await session.execute(text(sql), _params(world))
        assert table


async def test_the_worker_cannot_read_the_clinic_tables_directly(
    worker_db: ClinicDatabase, world: SeedResult
) -> None:
    for table in ("clinic.staff_profiles", "clinic.patient_ownership", "clinic.on_call_contacts"):
        with pytest.raises(ProgrammingError, match="permission denied"):
            async with worker_db.session() as session:
                await session.execute(text(f"SELECT * FROM {table}"))  # noqa: S608 - fixed names


async def test_the_worker_reads_the_staff_tables_through_the_views(
    db: ClinicDatabase, worker_db: ClinicDatabase, world: SeedResult
) -> None:
    await _seed_clinic_rows(db, world)
    async with worker_db.session() as session:
        staff = (
            await session.execute(
                text("SELECT user_id, skills, capacity, languages FROM clinic_agent.staff_profile")
            )
        ).one()
        owner = (
            await session.execute(text("SELECT cs_owner, doctor FROM clinic_agent.patient_ownership"))
        ).one()
        on_call = (
            await session.execute(text("SELECT zalo_number, is_fixture FROM clinic_agent.on_call_contact"))
        ).one()
    assert staff.user_id == world.users["cs.thu"]
    assert staff.skills == ["laser"]
    assert (staff.capacity, staff.languages) == (5, ["vi"])
    assert (owner.cs_owner, owner.doctor) == (world.users["cs.thu"], world.users["doctor.mai"])
    assert (on_call.zalo_number, on_call.is_fixture) == ("0000000003", True)


async def test_the_worker_cannot_write_through_the_views(
    db: ClinicDatabase, worker_db: ClinicDatabase, world: SeedResult
) -> None:
    await _seed_clinic_rows(db, world)
    statements = (
        "UPDATE clinic_agent.staff_profile SET capacity = 99",
        "DELETE FROM clinic_agent.on_call_contact",
        "INSERT INTO clinic_agent.patient_ownership (clinic_id, patient_id) VALUES (:c, :p)",
    )
    for sql in statements:
        with pytest.raises(ProgrammingError, match="permission denied"):
            async with worker_db.session() as session:
                await session.execute(text(sql), _params(world))


async def test_be_app_manages_the_three_clinic_tables_and_they_stay_audited_by_version(
    db: ClinicDatabase, world: SeedResult
) -> None:
    await _seed_clinic_rows(db, world)
    async with db.session() as session:
        profile = await session.scalar(select(StaffProfile))
        assert profile is not None
        profile.capacity = 3
    async with db.session() as session:
        profile = await session.scalar(select(StaffProfile))
        assert profile is not None
        assert (profile.capacity, profile.version) == (3, 2)
        await session.delete(profile)


async def test_the_worker_writes_every_agent_table(
    db: ClinicDatabase, worker_db: ClinicDatabase, world: SeedResult
) -> None:
    clinic = world.clinic_id
    patient = world.patients["P025"]
    async with worker_db.session() as session:
        agent = await ensure_care_agent(session, patient, clinic_id=clinic)
        agent.trust_scores = {"faq": 2}
        session.add(
            CareMemory(
                clinic_id=clinic, care_agent_id=agent.id, fact="thích nhắn buổi tối (mẫu)", source="staff"
            )
        )
        session.add(ConversationControl(clinic_id=clinic, patient_id=patient))
        session.add(
            HandoffRequest(
                clinic_id=clinic, patient_id=patient, reason="cần người (mẫu)", depth="D4", confidence=0.3
            )
        )
        session.add(AgentTask(clinic_id=clinic, care_agent_id=agent.id, agent_id="knowledge"))
        session.add(
            ActionLog(clinic_id=clinic, care_agent_id=agent.id, action_type="faq", disposition="auto_sent")
        )
        session.add(
            Skill(
                clinic_id=clinic,
                name="handoff",
                instruction="hướng dẫn (mẫu)",
                enabled_for_profiles=["patient_channel"],
            )
        )
    async with (
        db.session() as session
    ):  # be_app sees the same rows, and the python defaults reached the database
        stored = await session.scalar(select(CareAgent).where(CareAgent.patient_id == patient))
        assert stored is not None
        assert stored.trust_scores == {"faq": 2}
        control = await session.scalar(select(ConversationControl))
        assert control is not None
        assert (control.state, control.auto_release_after, control.version) == ("AUTO", None, 1)
        request = await session.scalar(select(HandoffRequest))
        assert request is not None
        assert (request.urgency, request.current_idx, request.candidates, request.outcome) == (
            "normal",
            0,
            [],
            None,
        )
        task = await session.scalar(select(AgentTask))
        assert task is not None
        assert (task.status, task.tokens, task.input) == ("queued", 0, {})
        log = await session.scalar(select(ActionLog))
        assert log is not None
        assert log.id >= 1
        assert log.at is not None


async def test_actions_log_ids_are_generated_for_both_runtime_roles(
    db: ClinicDatabase, worker_db: ClinicDatabase, world: SeedResult
) -> None:
    """quyền USAGE trên sequence (identity) của agent.actions_log cho cả be_app và agent_worker"""
    async with db.session() as session:
        agent = await ensure_care_agent(session, world.patients["P025"])
    ids: list[int] = []
    for database in (db, worker_db):
        async with database.session() as session:
            row = ActionLog(
                clinic_id=world.clinic_id, care_agent_id=agent.id, action_type="x", disposition="paused"
            )
            session.add(row)
            await session.flush()
            ids.append(row.id)
    assert len(set(ids)) == 2
