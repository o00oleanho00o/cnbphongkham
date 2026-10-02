"""Postgres side of staff routing and the 24/7 contact (package M, step M2c). New module (not a port).

* ``SqlRoutingStore`` (``RoutingStore``): the routing columns of ``agent.handoff_requests``. ``save_routing``
  locks the row (``SELECT ... FOR UPDATE``), checks that the request is still open and still at
  ``expected_idx``, writes ``candidates`` / ``current_idx`` / ``current_notified_at`` / ``outcome`` and its
  ``actions_log`` line in ONE transaction; a caller that lost a race gets ``None`` and does nothing.
* ``SqlRoutingDirectory`` (``RoutingDirectory``) and ``SqlOnCallSource`` (``OnCallSource``): the staff
  profiles, patient ownership and on-call rows. The worker role (``agent_worker``) has no privilege on schema
  ``clinic`` and reads the SELECT-only views ``clinic_agent.staff_profile``, ``patient_ownership`` and
  ``on_call_contact``; the API role (``be_app``, where staff accept and decline) reads the tables. ``role``
  picks the door; the columns are the same. The load of a person is the number of conversations in ``STAFF``
  state she owns, counted in the same query (no query per person).
* ``SqlRoutingConfigSource`` (``RoutingConfigSource``): the row ``agent.skills`` ``routing``; read on EVERY
  use, defaults when the row is missing or does not validate. ``ensure_routing_config`` seeds it with the
  temporary defaults (idempotent, an existing row edited on the dashboard is left alone).
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import cast, func, select, text
from sqlalchemy.dialects.postgresql import JSONPATH
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from pema.care.control_store import request_snapshot
from pema.care.models import (
    PATIENT_CHANNEL_PROFILE,
    ActionDisposition,
    ActionLog,
    CareAgent,
    HandoffRequest,
    Skill,
)
from pema.care.ports import HandoffRequestSnapshot
from pema.care.routing_types import (
    ROUTING_SKILL_NAME,
    CandidateStatus,
    DeclineRecord,
    OnCallRow,
    Ownership,
    RoutingConfig,
    StaffInfo,
    candidates_from_json,
    routing_config_from_row,
)
from pema.care.store import SqlCareStore
from pema.core.db import ClinicDatabase

logger = logging.getLogger(__name__)

type Door = Literal["worker", "app"]

ROUTING_INSTRUCTION = (
    "Staff routing, SLA, on-call texts and reminder rules (configuration only; no model instruction)."
)

_DECLINED_PATH = '$[*] ? (@.status == "declined")'
"""jsonpath: a candidate that declined (the date filter is done on ``declined_at`` in Python, so the
database clock never mixes with the injected one)."""

_STAFF_VIEW = """
    SELECT s.user_id, s.role, s.skills, s.shift, s.capacity, s.languages, COALESCE(l.n, 0) AS load
      FROM clinic_agent.staff_profile s
      LEFT JOIN (SELECT staff_owner, count(*) AS n FROM agent.conversation_control
                  WHERE state = 'STAFF' GROUP BY staff_owner) l ON l.staff_owner = s.user_id
     WHERE s.clinic_id = :clinic_id"""
_STAFF_TABLE = """
    SELECT s.user_id, s.role, s.skills, s.shift, s.capacity, s.languages, COALESCE(l.n, 0) AS load
      FROM clinic.staff_profiles s
      LEFT JOIN (SELECT staff_owner, count(*) AS n FROM agent.conversation_control
                  WHERE state = 'STAFF' GROUP BY staff_owner) l ON l.staff_owner = s.user_id
     WHERE s.clinic_id = :clinic_id"""
_OWNERSHIP_VIEW = "SELECT cs_owner, doctor FROM clinic_agent.patient_ownership WHERE patient_id = :patient_id"
_OWNERSHIP_TABLE = "SELECT cs_owner, doctor FROM clinic.patient_ownership WHERE patient_id = :patient_id"
_ON_CALL_VIEW = """
    SELECT id, zalo_number, owner, valid_from, valid_to, active, is_fixture
      FROM clinic_agent.on_call_contact WHERE clinic_id = :clinic_id AND active"""
_ON_CALL_TABLE = """
    SELECT id, zalo_number, owner, valid_from, valid_to, active, is_fixture
      FROM clinic.on_call_contacts WHERE clinic_id = :clinic_id AND active"""


class SqlRoutingStore:
    def __init__(self, db: ClinicDatabase) -> None:
        self._db = db
        self._care = SqlCareStore(db)

    async def get_request(self, request_id: UUID) -> HandoffRequestSnapshot | None:
        async with self._db.session() as session:
            row = await session.get(HandoffRequest, request_id)
            if row is None:
                return None
            agent_id = await _agent_id(session, row.patient_id)
            return request_snapshot(row, agent_id)

    async def list_unresolved_requests(self, *, limit: int) -> Sequence[HandoffRequestSnapshot]:
        async with self._db.session() as session:
            rows = list(
                await session.scalars(
                    select(HandoffRequest)
                    .where(HandoffRequest.outcome.is_(None))
                    .order_by(HandoffRequest.created_at)
                    .limit(limit)
                )
            )
            if not rows:
                return []
            pairs = await session.execute(
                select(CareAgent.patient_id, CareAgent.id).where(
                    CareAgent.patient_id.in_([row.patient_id for row in rows])
                )
            )
            agents = dict(pairs.all())
            return [request_snapshot(row, agents[row.patient_id]) for row in rows]

    async def save_routing(
        self,
        request_id: UUID,
        *,
        expected_idx: int,
        candidates: Sequence[Mapping[str, object]],
        current_idx: int,
        notified_at: datetime | None,
        outcome: str | None,
        log_action: str,
        at: datetime,
    ) -> HandoffRequestSnapshot | None:
        async with self._db.session() as session:
            row = await session.scalar(
                select(HandoffRequest)
                .where(HandoffRequest.id == request_id, HandoffRequest.outcome.is_(None))
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if row is None or row.current_idx != expected_idx:
                return None
            agent = await session.scalar(select(CareAgent).where(CareAgent.patient_id == row.patient_id))
            if agent is None:
                return None
            row.candidates = [dict(item) for item in candidates]
            row.current_idx = current_idx
            row.current_notified_at = notified_at
            if outcome is not None:
                row.outcome = outcome
                row.resolved_at = at
            session.add(
                ActionLog(
                    clinic_id=row.clinic_id,
                    care_agent_id=agent.id,
                    action_type=log_action,
                    depth=row.depth,
                    disposition=ActionDisposition.PAUSED.value,
                    at=at,
                )
            )
            await session.flush()
            return request_snapshot(row, agent.id)

    async def record_action(
        self,
        care_agent_id: UUID,
        *,
        action_type: str,
        disposition: str,
        depth: str | None,
        at: datetime,
    ) -> None:
        await self._care.record_action(
            care_agent_id, action_type=action_type, disposition=disposition, depth=depth, at=at
        )

    async def declines_since(self, since: datetime, *, limit: int) -> Sequence[DeclineRecord]:
        async with self._db.session() as session:
            rows = list(
                await session.scalars(
                    select(HandoffRequest)
                    .where(func.jsonb_path_exists(HandoffRequest.candidates, cast(_DECLINED_PATH, JSONPATH)))
                    .order_by(HandoffRequest.created_at)
                    .limit(limit)
                )
            )
        records: list[DeclineRecord] = []
        for row in rows:
            for candidate in candidates_from_json(row.candidates):
                if candidate.status is not CandidateStatus.DECLINED:
                    continue
                if candidate.declined_at is None or candidate.declined_at < since:
                    continue
                records.append(
                    DeclineRecord(
                        request_id=row.id,
                        user_id=candidate.user_id,
                        required_skill=row.required_skill,
                        depth=row.depth,
                        reason=candidate.decline_reason,
                        declined_at=candidate.declined_at,
                    )
                )
        return records


class SqlRoutingDirectory:
    def __init__(self, db: ClinicDatabase, *, role: Door = "worker") -> None:
        self._db = db
        self._staff = _STAFF_VIEW if role == "worker" else _STAFF_TABLE
        self._ownership = _OWNERSHIP_VIEW if role == "worker" else _OWNERSHIP_TABLE

    async def list_staff(self, clinic_id: UUID) -> Sequence[StaffInfo]:
        async with self._db.session() as session:
            result = await session.execute(text(self._staff), {"clinic_id": clinic_id})
            return [
                StaffInfo(
                    user_id=row.user_id,
                    role=row.role,
                    skills=tuple(row.skills),
                    shift=dict(row.shift),
                    capacity=row.capacity,
                    load=int(row.load),
                    languages=tuple(row.languages),
                )
                for row in result
            ]

    async def ownership(self, patient_id: UUID) -> Ownership:
        async with self._db.session() as session:
            row = (await session.execute(text(self._ownership), {"patient_id": patient_id})).first()
        return Ownership() if row is None else Ownership(cs_owner=row.cs_owner, doctor=row.doctor)


class SqlOnCallSource:
    def __init__(self, db: ClinicDatabase, *, role: Door = "worker") -> None:
        self._db = db
        self._query = _ON_CALL_VIEW if role == "worker" else _ON_CALL_TABLE

    async def active_contacts(self, clinic_id: UUID) -> Sequence[OnCallRow]:
        async with self._db.session() as session:
            result = await session.execute(text(self._query), {"clinic_id": clinic_id})
            return [
                OnCallRow(
                    id=row.id,
                    zalo_number=row.zalo_number,
                    owner=row.owner,
                    valid_from=row.valid_from,
                    valid_to=row.valid_to,
                    active=row.active,
                    is_fixture=row.is_fixture,
                )
                for row in result
            ]


class SqlRoutingConfigSource:
    def __init__(self, db: ClinicDatabase) -> None:
        self._db = db

    async def get(self, clinic_id: UUID) -> RoutingConfig:
        async with self._db.session() as session:
            raw = await session.scalar(
                select(Skill.classifier_config).where(
                    Skill.clinic_id == clinic_id, Skill.name == ROUTING_SKILL_NAME
                )
            )
        if raw is None:
            return RoutingConfig()
        try:
            return routing_config_from_row(raw)
        except ValidationError:
            logger.error("routing classifier_config is invalid; defaults are used")
            return RoutingConfig()


async def ensure_routing_config(session: AsyncSession, clinic_id: UUID) -> None:
    """Seed ``agent.skills`` ``routing`` with the temporary defaults (``pending_doctor_approval = true``)."""
    values: dict[str, Any] = {
        "clinic_id": clinic_id,
        "name": ROUTING_SKILL_NAME,
        "instruction": ROUTING_INSTRUCTION,
        "classifier_config": RoutingConfig().model_dump(mode="json"),
        "enabled_for_profiles": [PATIENT_CHANNEL_PROFILE],
    }
    await session.execute(
        pg_insert(Skill).values(**values).on_conflict_do_nothing(index_elements=[Skill.clinic_id, Skill.name])
    )


async def _agent_id(session: AsyncSession, patient_id: UUID) -> UUID:
    found = await session.scalar(select(CareAgent.id).where(CareAgent.patient_id == patient_id))
    if found is None:
        raise LookupError("no care agent for this patient")
    return found
