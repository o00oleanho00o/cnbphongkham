"""Postgres side of the specialists: ``agent.tasks``, the checklist skill row, the seed and the adapters.

New module (not a port). Same conventions as ``pema.care.store``: one short unit of work per call, the role
``agent_worker`` is enough (``agent.*`` is granted to both runtime roles), single tenant (``clinic_id`` is the
installation id, no row level security).

* ``SqlTaskStore``: ``agent.tasks``. The tree is a root row per care turn (``parent_id`` NULL, ``agent_id``
  ``care-turn``) and one child per delegation. ``create_child`` refuses a parent that is itself a child
  (``DepthError``): depth 1 is checked here as well as in the tool set. (A database trigger would be a third
  lock; it needs a migration on the shared chain, see the open items of the M4 report.)
* ``SqlChecklistSource``: the row ``review_checklist`` of ``agent.skills``; a missing or unreadable row
  gives the
  default checklist (pending doctor approval).
* ``seed_specialists``: the three records of ``agent.agents`` and the default checklist row. Idempotent: an
  existing record is left alone EXCEPT that ``delegate`` is put back into its deny list if someone removed it.
* ``SqlAppointmentConfirmPolicy``: M3's ``effective_level`` for ``appointment_confirm``.
* ``StoreKnowledgeAccess``: D3's ``PostgresKnowledgeStore`` narrowed to ``KnowledgeAccess``.
"""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from pema.care.autonomy import ActionType, Level, effective_level
from pema.care.models import AgentTask, CareAgent, Skill, TaskStatus
from pema.care.ports import DepthError, KbSourceBrief
from pema.care.specialists.knowledge import knowledge_spec
from pema.care.specialists.reviewer import (
    CHECKLIST_INSTRUCTION,
    CHECKLIST_SKILL_NAME,
    DEFAULT_CHECKLIST,
    ReviewChecklist,
    reviewer_spec,
)
from pema.care.specialists.scheduler import scheduler_spec
from pema.care.specialists.spec import DELEGATE_TOOL, KNOWLEDGE_ID, SpecialistSpec
from pema.care.task_result import TaskResult
from pema.core.db import ClinicDatabase, get_installation_clinic_id
from pema.knowledge.postgres_knowledge_store import PostgresKnowledgeStore
from pema_contracts.common import JsonObject
from pema_contracts.knowledge import KbHit
from pema_contracts.policy import PolicyProfileKey

ROOT_AGENT_ID = "care-turn"


def all_specs() -> tuple[SpecialistSpec, ...]:
    return (scheduler_spec(), knowledge_spec(), reviewer_spec())


# ====================================================================================== tasks
class SqlTaskStore:
    def __init__(self, db: ClinicDatabase) -> None:
        self._db = db

    async def create_root(self, care_agent_id: UUID, *, started_at: datetime, deadline_at: datetime) -> UUID:
        async with self._db.session() as session:
            clinic_id = await session.scalar(select(CareAgent.clinic_id).where(CareAgent.id == care_agent_id))
            if clinic_id is None:
                raise LookupError("care agent not found")
            row = AgentTask(
                clinic_id=clinic_id,
                parent_id=None,
                care_agent_id=care_agent_id,
                agent_id=ROOT_AGENT_ID,
                status=TaskStatus.RUNNING.value,
                started_at=started_at,
                deadline_at=deadline_at,
            )
            session.add(row)
            await session.flush()
            return row.id

    async def create_child(
        self,
        parent_id: UUID,
        *,
        agent_id: str,
        input: JsonObject,
        started_at: datetime,
        deadline_at: datetime,
    ) -> UUID:
        async with self._db.session() as session:
            parent = await session.get(AgentTask, parent_id)
            if parent is None:
                raise LookupError("parent task not found")
            if parent.parent_id is not None:
                raise DepthError("a delegation cannot delegate (depth 1)")
            row = AgentTask(
                clinic_id=parent.clinic_id,
                parent_id=parent.id,
                care_agent_id=parent.care_agent_id,
                agent_id=agent_id,
                status=TaskStatus.RUNNING.value,
                input=input,
                started_at=started_at,
                deadline_at=deadline_at,
            )
            session.add(row)
            await session.flush()
            return row.id

    async def finish(
        self,
        task_id: UUID,
        *,
        status: TaskStatus,
        result: TaskResult | None,
        tokens: int,
        cost: Decimal,
        finished_at: datetime,
        error: str | None = None,
    ) -> None:
        async with self._db.session() as session:
            row = await session.get(AgentTask, task_id)
            if row is None:
                raise LookupError("task not found")
            row.status = status.value
            row.result = None if result is None else result.model_dump(mode="json")
            row.tokens = tokens
            row.cost = cost
            row.finished_at = finished_at
            row.error = error

    async def finish_root(self, task_id: UUID, *, finished_at: datetime) -> None:
        """Close the turn's own row (``done`` unless a child already needs a person)."""
        async with self._db.session() as session:
            row = await session.get(AgentTask, task_id)
            if row is None:
                raise LookupError("task not found")
            needs_human = await session.scalar(
                select(AgentTask.id)
                .where(AgentTask.parent_id == task_id, AgentTask.status == TaskStatus.NEEDS_HUMAN.value)
                .limit(1)
            )
            row.status = TaskStatus.NEEDS_HUMAN.value if needs_human is not None else TaskStatus.DONE.value
            row.finished_at = finished_at


# ================================================================================== checklist
class SqlChecklistSource:
    def __init__(self, db: ClinicDatabase) -> None:
        self._db = db

    async def get_checklist(self) -> ReviewChecklist:
        async with self._db.session() as session:
            config = await session.scalar(
                select(Skill.classifier_config).where(Skill.name == CHECKLIST_SKILL_NAME)
            )
        return ReviewChecklist.from_config(config)


# ======================================================================================= seed
_GET_RECORD = text("SELECT disabled_tools FROM agent.agents WHERE clinic_id = :clinic_id AND id = :id")
_INSERT_RECORD = text(
    """
    INSERT INTO agent.agents (clinic_id, id, icon, name, persona, max_steps, disabled_tools, policy_profile)
    VALUES (:clinic_id, :id, :icon, :name, :persona, :max_steps, CAST(:disabled AS jsonb), :policy_profile)
    ON CONFLICT (clinic_id, id) DO NOTHING
    """
)
_SET_DISABLED = text(
    "UPDATE agent.agents SET disabled_tools = CAST(:disabled AS jsonb) WHERE clinic_id = :clinic_id AND "
    "id = :id"
)


async def seed_specialists(db: ClinicDatabase, *, clinic_id: UUID | None = None) -> list[str]:
    """Create the three specialist records and the default checklist row. Returns the agent ids."""
    clinic = clinic_id or await get_installation_clinic_id(db)
    async with db.session() as session:
        for spec in all_specs():
            await session.execute(
                _INSERT_RECORD,
                {
                    "clinic_id": clinic,
                    "id": spec.agent_id,
                    "icon": spec.icon,
                    "name": spec.name,
                    "persona": spec.persona,
                    "max_steps": spec.max_steps,
                    "disabled": json.dumps(spec.disabled_tools()),
                    "policy_profile": spec.policy_profile.value,
                },
            )
            stored = (
                await session.execute(_GET_RECORD, {"clinic_id": clinic, "id": spec.agent_id})
            ).scalar_one()
            raw: Any = json.loads(stored) if isinstance(stored, str) else stored
            disabled = [str(key) for key in raw]
            if DELEGATE_TOOL not in disabled:
                await session.execute(
                    _SET_DISABLED,
                    {
                        "clinic_id": clinic,
                        "id": spec.agent_id,
                        "disabled": json.dumps([*disabled, DELEGATE_TOOL]),
                    },
                )
        await session.execute(
            pg_insert(Skill)
            .values(
                clinic_id=clinic,
                name=CHECKLIST_SKILL_NAME,
                instruction=CHECKLIST_INSTRUCTION,
                classifier_config=DEFAULT_CHECKLIST.to_config(),
                enabled_for_profiles=[PolicyProfileKey.PATIENT_CHANNEL.value],
            )
            .on_conflict_do_nothing(index_elements=[Skill.clinic_id, Skill.name])
        )
    return [spec.agent_id for spec in all_specs()]


# ===================================================================================== adapters
class SqlAppointmentConfirmPolicy:
    """``AppointmentConfirmPolicy``: L1 or better ``appointment_confirm`` for this care agent right now."""

    def __init__(self, db: ClinicDatabase) -> None:
        self._db = db

    async def l1_applies(self, care_agent_id: UUID, now: datetime) -> bool:
        async with self._db.session() as session:
            care_agent = await session.get(CareAgent, care_agent_id)
            if care_agent is None:
                return False
            level = effective_level(care_agent, ActionType.APPOINTMENT_CONFIRM.value, now)
        return level.rank >= Level.L1.rank


class StoreKnowledgeAccess:
    """``KnowledgeAccess`` over D3's ``PostgresKnowledgeStore`` for the ``care-knowledge`` agent.

    ``only_approved`` is passed as ``chi_da_duyet``: the keyword the Protocol of D3 cannot carry (see the
    docstring of ``PostgresKnowledgeStore.search``; the specialist record is ``staff_assistant`` and would
    otherwise read unapproved sources while its answer goes to a patient).
    """

    def __init__(self, store: PostgresKnowledgeStore, clinic_id: UUID, agent_id: str = KNOWLEDGE_ID) -> None:
        self._store = store
        self._clinic_id = clinic_id
        self._agent_id = agent_id

    async def search(self, question: str, *, only_approved: bool, limit: int = 5) -> list[KbHit]:
        return await self._store.search(
            self._clinic_id,
            question=question,
            agent_id=self._agent_id,
            limit=limit,
            chi_da_duyet=only_approved,
        )

    async def ingest_text(self, name: str, text: str) -> KbSourceBrief:
        source = await self._store.create_text_source(self._clinic_id, name=name, text=text)
        return KbSourceBrief(source.id, source.name, source.status.value, source.approved_by_clinical_owner)

    async def list_sources(self) -> list[KbSourceBrief]:
        sources = await self._store.list_sources(self._clinic_id)
        return [
            KbSourceBrief(
                s.id,
                s.name,
                s.status.value,
                s.approved_by_clinical_owner,
            )
            for s in sources
        ]
