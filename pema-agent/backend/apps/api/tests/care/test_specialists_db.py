"""Specialists over Postgres: seed, ``agent.tasks`` tree, checklist row, audit rows (package M, step M4).

New tests. Need ``PEMA_TEST_DATABASE_URL`` (skipped otherwise). Single tenant: no RLS; ``clinic_id`` is the
installation id.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import Engine, text

from pema.care.autonomy import KillSwitchState
from pema.care.budget import TurnBudget
from pema.care.models import TaskStatus
from pema.care.pairing import ensure_care_agent
from pema.care.ports import DepthError
from pema.care.specialists.delegate import DelegationService
from pema.care.specialists.reviewer import (
    CHECKLIST_SKILL_NAME,
    DEFAULT_CHECKLIST,
    ChecklistRunner,
)
from pema.care.specialists.scope import CareTurnScope
from pema.care.specialists.spec import DELEGATE_TOOL, KNOWLEDGE_ID, REVIEWER_ID, SCHEDULER_ID
from pema.care.specialists.store import (
    SqlAppointmentConfirmPolicy,
    SqlChecklistSource,
    SqlTaskStore,
    all_specs,
    seed_specialists,
)
from pema.care.specialists.toolkit import SpecialistToolkit
from pema.care.store import SqlCareStore
from pema.care.task_result import TaskResult
from pema.clinic.actions.seed_demo import SeedResult
from pema.config.agent_store import AgentStoreImpl
from pema.core.db import ClinicDatabase, get_installation_clinic_id

pytestmark = pytest.mark.db

NOW = datetime(2026, 10, 3, 10, 0, tzinfo=UTC)


def _scalar(admin: Engine, sql: str, **params: Any) -> Any:
    with admin.connect() as conn:
        return conn.execute(text(sql), params).scalar_one()


async def _care_agent(db: ClinicDatabase, world: SeedResult, code: str = "P025") -> UUID:
    async with db.session() as session:
        return (await ensure_care_agent(session, world.patients[code])).id


# ---------------------------------------------------------------------------------------------- seed
async def test_the_seed_creates_the_three_specialist_records_with_delegate_denied(
    db: ClinicDatabase, world: SeedResult
) -> None:
    ids = await seed_specialists(db)
    assert ids == [SCHEDULER_ID, KNOWLEDGE_ID, REVIEWER_ID]
    clinic_id = await get_installation_clinic_id(db)
    store = AgentStoreImpl(db)
    for spec in all_specs():
        record = await store.get_agent(clinic_id, spec.agent_id)
        assert record is not None
        assert DELEGATE_TOOL in record.disabled_tools
        assert not set(record.disabled_tools) & spec.allowed_tools
        assert record.policy_profile is spec.policy_profile
        assert record.is_default is False


async def test_the_seed_is_idempotent_and_puts_delegate_back_when_someone_removed_it(
    db: ClinicDatabase, world: SeedResult, admin: Engine
) -> None:
    await seed_specialists(db)
    with admin.begin() as conn:
        conn.execute(
            text("UPDATE agent.agents SET disabled_tools = '[]'::jsonb, persona = 'edited' WHERE id = :id"),
            {"id": SCHEDULER_ID},
        )
    await seed_specialists(db)
    await seed_specialists(db)
    assert _scalar(admin, "SELECT count(*) FROM agent.agents WHERE id LIKE 'care-%'") == 3
    disabled = _scalar(admin, "SELECT disabled_tools FROM agent.agents WHERE id = :id", id=SCHEDULER_ID)
    assert DELEGATE_TOOL in json.loads(disabled) if isinstance(disabled, str) else DELEGATE_TOOL in disabled
    assert _scalar(admin, "SELECT persona FROM agent.agents WHERE id = :id", id=SCHEDULER_ID) == "edited"


# -------------------------------------------------------------------------------------------- checklist
async def test_the_default_checklist_row_is_stored_pending_and_read_back(
    db: ClinicDatabase, worker_db: ClinicDatabase, world: SeedResult, admin: Engine
) -> None:
    await seed_specialists(db)
    assert _scalar(admin, "SELECT count(*) FROM agent.skills WHERE name = :n", n=CHECKLIST_SKILL_NAME) == 1
    config = _scalar(
        admin, "SELECT classifier_config FROM agent.skills WHERE name = :n", n=CHECKLIST_SKILL_NAME
    )
    assert (json.loads(config) if isinstance(config, str) else config)["pending_doctor_approval"] is True
    checklist = await SqlChecklistSource(worker_db).get_checklist()
    assert checklist == DEFAULT_CHECKLIST


async def test_a_checklist_the_doctor_edited_is_what_the_reviewer_uses(
    db: ClinicDatabase, worker_db: ClinicDatabase, world: SeedResult, admin: Engine
) -> None:
    await seed_specialists(db)
    edited = {"pending_doctor_approval": False, "enabled": {"no_pii": False}, "diagnosis_terms": ["xyz"]}
    with admin.begin() as conn:
        conn.execute(
            text("UPDATE agent.skills SET classifier_config = CAST(:c AS jsonb) WHERE name = :n"),
            {"c": json.dumps(edited), "n": CHECKLIST_SKILL_NAME},
        )
    checklist = await SqlChecklistSource(worker_db).get_checklist()
    assert checklist.pending_doctor_approval is False
    assert checklist.is_enabled("no_pii") is False
    with admin.begin() as conn:
        conn.execute(
            text("UPDATE agent.skills SET classifier_config = '{\"enabled\": 5}'::jsonb WHERE name = :n"),
            {"n": CHECKLIST_SKILL_NAME},
        )
    assert await SqlChecklistSource(worker_db).get_checklist() == DEFAULT_CHECKLIST


# ------------------------------------------------------------------------------------------ the tree
async def test_the_tasks_tree_in_the_database_has_depth_at_most_one(
    db: ClinicDatabase, worker_db: ClinicDatabase, world: SeedResult, admin: Engine
) -> None:
    care_agent_id = await _care_agent(db, world)
    tasks = SqlTaskStore(worker_db)
    root = await tasks.create_root(care_agent_id, started_at=NOW, deadline_at=NOW + timedelta(minutes=3))
    first = await tasks.create_child(
        root, agent_id=SCHEDULER_ID, input={"task_chars": 12}, started_at=NOW, deadline_at=NOW
    )
    second = await tasks.create_child(root, agent_id=KNOWLEDGE_ID, input={}, started_at=NOW, deadline_at=NOW)
    with pytest.raises(DepthError):
        await tasks.create_child(first, agent_id=KNOWLEDGE_ID, input={}, started_at=NOW, deadline_at=NOW)
    await tasks.finish(
        first,
        status=TaskStatus.DONE,
        result=TaskResult(summary="ok", confidence=0.7),
        tokens=321,
        cost=Decimal("0.001234"),
        finished_at=NOW + timedelta(seconds=2),
    )
    await tasks.finish(
        second,
        status=TaskStatus.NEEDS_HUMAN,
        result=None,
        tokens=0,
        cost=Decimal(0),
        finished_at=NOW,
        error="budget_exhausted:deadline",
    )
    await tasks.finish_root(root, finished_at=NOW + timedelta(seconds=3))
    too_deep = _scalar(
        admin,
        "SELECT count(*) FROM agent.tasks c JOIN agent.tasks p ON p.id = c.parent_id "
        "WHERE p.parent_id IS NOT NULL",
    )
    assert too_deep == 0
    assert _scalar(admin, "SELECT count(*) FROM agent.tasks WHERE parent_id = :r", r=root) == 2
    assert _scalar(admin, "SELECT status FROM agent.tasks WHERE id = :r", r=root) == "needs_human"
    assert _scalar(admin, "SELECT tokens FROM agent.tasks WHERE id = :r", r=first) == 321
    result = _scalar(admin, "SELECT result FROM agent.tasks WHERE id = :r", r=first)
    assert (json.loads(result) if isinstance(result, str) else result)["summary"] == "ok"


# ------------------------------------------------------------------------------------ end to end in SQL
async def test_a_delegation_over_postgres_writes_the_task_rows_and_the_budget_audit_row(
    db: ClinicDatabase, worker_db: ClinicDatabase, world: SeedResult, admin: Engine
) -> None:
    care_agent_id = await _care_agent(db, world)
    care_store = SqlCareStore(worker_db)
    snapshot = await care_store.get_care_agent(care_agent_id)
    assert snapshot is not None
    scope = CareTurnScope(
        care_agent=snapshot,
        patient_ref="P025",
        budget=TurnBudget(max_specialists=1),
        turn_key="turn-db-1",
    )
    service = DelegationService(
        specs={s.agent_id: s for s in all_specs()},
        runners={REVIEWER_ID: ChecklistRunner(SqlChecklistSource(worker_db))},
        toolkit=SpecialistToolkit(),
        tasks=SqlTaskStore(worker_db),
        store=care_store,
        kill_switch=KillSwitchState,
    )
    await seed_specialists(db)
    first = await service.delegate(scope, "reviewer", "Chị gọi 0901 234 567 nhé.", None)
    second = await service.delegate(scope, "reviewer", "Nhắc lịch mai.", None)
    assert (first.needs_human, second.needs_human) == (True, True)
    assert _scalar(admin, "SELECT count(*) FROM agent.tasks WHERE parent_id IS NULL") == 1
    assert _scalar(admin, "SELECT count(*) FROM agent.tasks WHERE parent_id IS NOT NULL") == 2
    statuses = _scalar(
        admin,
        "SELECT string_agg(status, ',' ORDER BY created_at, status) FROM agent.tasks WHERE parent_id IS NOT NULL",
    )
    assert set(statuses.split(",")) == {"needs_human"}
    kinds = _scalar(
        admin,
        "SELECT string_agg(action_type || '/' || disposition, ',') FROM agent.actions_log WHERE care_agent_id = :c",
        c=care_agent_id,
    )
    assert kinds == "budget_exhausted:max_specialists/paused"


# --------------------------------------------------------------------------------- confirm eligibility
async def test_appointment_confirm_l1_applies_only_with_an_explicit_l1_entry(
    db: ClinicDatabase, worker_db: ClinicDatabase, world: SeedResult, admin: Engine
) -> None:
    care_agent_id = await _care_agent(db, world)
    policy = SqlAppointmentConfirmPolicy(worker_db)
    assert await policy.l1_applies(care_agent_id, NOW) is False
    with admin.begin() as conn:
        conn.execute(
            text(
                'UPDATE agent.care_agents SET autonomy_levels = \'{"appointment_confirm": "L1"}\'::jsonb WHERE id = :i'
            ),
            {"i": care_agent_id},
        )
    assert await policy.l1_applies(care_agent_id, NOW) is True
    with admin.begin() as conn:
        conn.execute(text("UPDATE agent.care_agents SET paused = true WHERE id = :i"), {"i": care_agent_id})
    assert await policy.l1_applies(care_agent_id, NOW) is False
    assert await policy.l1_applies(UUID(int=0), NOW) is False
