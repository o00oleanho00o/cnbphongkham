"""Pairing of patient and care agent (package M, step M1). New tests (no zalo-agent original).

Needs ``PEMA_TEST_DATABASE_URL`` (skipped otherwise). Single tenant: there is no row level security, the
"another clinic" case is the foreign key to ``clinic.clinic`` (a second clinic cannot exist).
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from pema.care.models import CareAgent
from pema.care.pairing import CareAgentPairing, ensure_care_agent
from pema.care.ports import PatientCreatedHook
from pema.clinic.actions.patients import create_patient
from pema.clinic.actions.seed_demo import SeedResult
from pema.core.db import ClinicDatabase
from pema_contracts.actions import ActionContext
from pema_contracts.patients import PatientCreate
from pema_contracts.roles import ActorType, Role

pytestmark = pytest.mark.db


def _reception(world: SeedResult) -> ActionContext:
    return ActionContext(
        clinic_id=world.clinic_id,
        actor_type=ActorType.USER,
        actor_user_id=world.users["reception.lan"],
        actor_role=Role.RECEPTION,
    )


async def _care_agents_of(db: ClinicDatabase, patient_id: object) -> list[CareAgent]:
    async with db.session() as session:
        rows = await session.scalars(select(CareAgent).where(CareAgent.patient_id == patient_id))
        return list(rows)


def test_the_pairing_implements_the_patient_created_hook() -> None:
    assert isinstance(CareAgentPairing(), PatientCreatedHook)


async def test_creating_a_patient_yields_exactly_one_care_agent(
    db: ClinicDatabase, world: SeedResult
) -> None:
    patient = await create_patient(db, _reception(world), PatientCreate(full_name="Bệnh nhân thử (mẫu)"))
    hook = CareAgentPairing()
    async with db.session() as session:
        await hook.on_patient_created(session, patient.id)
    agents = await _care_agents_of(db, patient.id)
    assert len(agents) == 1
    agent = agents[0]
    assert agent.clinic_id == world.clinic_id
    assert agent.profile == "patient_channel"
    assert agent.autonomy_levels == {}  # empty = L0 everywhere
    assert agent.autonomy_override is None
    assert agent.paused is False
    assert agent.version == 1


async def test_calling_the_hook_again_creates_none(db: ClinicDatabase, world: SeedResult) -> None:
    patient = await create_patient(db, _reception(world), PatientCreate(full_name="Bệnh nhân thử hai (mẫu)"))
    hook = CareAgentPairing()
    async with db.session() as session:
        await hook.on_patient_created(session, patient.id)
    first = (await _care_agents_of(db, patient.id))[0]
    async with db.session() as session:
        await hook.on_patient_created(session, patient.id)
        again = await ensure_care_agent(session, patient.id)
    assert again.id == first.id
    agents = await _care_agents_of(db, patient.id)
    assert [a.id for a in agents] == [first.id]


async def test_concurrent_pairing_of_one_patient_makes_one_care_agent(
    db: ClinicDatabase, world: SeedResult
) -> None:
    patient = await create_patient(
        db, _reception(world), PatientCreate(full_name="Bệnh nhân song song (mẫu)")
    )

    async def pair() -> object:
        async with db.session() as session:
            return (await ensure_care_agent(session, patient.id)).id

    ids = await asyncio.gather(*(pair() for _ in range(6)))
    assert len(set(ids)) == 1
    assert len(await _care_agents_of(db, patient.id)) == 1


async def test_the_pairing_rolls_back_with_the_unit_of_work(db: ClinicDatabase, world: SeedResult) -> None:
    patient = await create_patient(db, _reception(world), PatientCreate(full_name="Bệnh nhân hủy (mẫu)"))
    with pytest.raises(RuntimeError, match="boom"):
        async with db.session() as session:
            await ensure_care_agent(session, patient.id)
            raise RuntimeError("boom")
    assert await _care_agents_of(db, patient.id) == []


async def test_an_unknown_patient_is_refused_by_the_database(db: ClinicDatabase, world: SeedResult) -> None:
    with pytest.raises(IntegrityError):
        async with db.session() as session:
            await ensure_care_agent(session, uuid4())


async def test_a_care_agent_cannot_belong_to_another_clinic(db: ClinicDatabase, world: SeedResult) -> None:
    """đơn tenant: không có clinic thứ hai, clinic_id lạ bị khóa ngoại từ chối (thay cho kiểm RLS)"""
    patient_id = world.patients["P025"]
    with pytest.raises(IntegrityError):
        async with db.session() as session:
            await ensure_care_agent(session, patient_id, clinic_id=uuid4())


async def test_the_worker_can_pair_through_the_same_function(
    worker_db: ClinicDatabase, db: ClinicDatabase, world: SeedResult
) -> None:
    """agent_worker không đọc được clinic.patient nhưng vẫn ghép được: khóa ngoại kiểm bằng quyền chủ bảng"""
    async with worker_db.session() as session:
        agent = await ensure_care_agent(session, world.patients["P026"], clinic_id=world.clinic_id)
    assert len(await _care_agents_of(db, world.patients["P026"])) == 1
    assert agent.clinic_id == world.clinic_id


async def test_pairing_does_not_need_an_open_session_afterwards(
    db: ClinicDatabase, world: SeedResult
) -> None:
    """expire_on_commit=False và eager_defaults: đọc created_at/updated_at sau commit không chạm DB"""
    async with db.session() as session:
        agent = await ensure_care_agent(session, world.patients["P027"])
    assert agent.created_at is not None
    assert agent.updated_at is not None
