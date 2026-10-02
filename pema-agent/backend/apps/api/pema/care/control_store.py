"""``ControlStore`` over Postgres (``agent.conversation_control``, ``handoff_requests``, ``care_memory``,
``care_agents``, ``actions_log``). New module (not a port).

Each method is ONE transaction that changes the state AND writes its ``actions_log`` line, so there is never a
transition without its audit line. The control row is locked (``SELECT ... FOR UPDATE``) before the state is
read: two staff accepting at once, or two events opening a round at once, serialise; the second sees the new
state (``InvalidTransitionError`` / ``created=False``). A patient with no row yet is AUTO: the row is
created with
``INSERT ... ON CONFLICT DO NOTHING`` and then locked. The partial unique index
``handoff_requests_one_open_idx`` is the second guard: at most one open round per patient, whatever the
code does.

``handoff_requests`` has no column for the context summary and the table of M1 is final, so the summary rides
in ``reason`` after a marker line (``pack_reason`` / ``unpack_reason`` are the only two places that know
this). A ``summary`` column would make both functions trivial; it is an open item for the next migration.

Works with either runtime role (the grants of ``m_0001_care_tables`` give both ``agent_worker`` and ``be_app``
read and write on ``agent.*``).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from pema.care.handoff_types import InvalidTransitionError, level_code
from pema.care.models import (
    ActionDisposition,
    ActionLog,
    CareAgent,
    CareMemory,
    ControlState,
    ConversationControl,
    HandoffOutcome,
    HandoffRequest,
    MemorySource,
)
from pema.care.ports import (
    CareAgentSnapshot,
    ControlSnapshot,
    HandoffRequestSnapshot,
    HandoffSpec,
    OpenedHandoff,
    ReleaseSpec,
)
from pema.care.store import SqlCareStore, snapshot_of
from pema.core.db import ClinicDatabase

SUMMARY_MARKER = "\n--- summary ---\n"


def pack_reason(reason: str, summary: str) -> str:
    return f"{reason}{SUMMARY_MARKER}{summary}" if summary else reason


def unpack_reason(stored: str) -> tuple[str, str]:
    reason, _, summary = stored.partition(SUMMARY_MARKER)
    return reason, summary


def _request_snapshot(row: HandoffRequest, care_agent_id: UUID) -> HandoffRequestSnapshot:
    reason, summary = unpack_reason(row.reason)
    return HandoffRequestSnapshot(
        id=row.id,
        patient_id=row.patient_id,
        care_agent_id=care_agent_id,
        reason=reason,
        summary=summary,
        depth=row.depth,
        confidence=row.confidence,
        required_skill=row.required_skill,
        urgency=row.urgency,
        candidates=tuple(row.candidates),
        current_idx=row.current_idx,
        accepted_by=row.accepted_by,
        outcome=row.outcome,
        created_at=row.created_at,
    )


def _control_snapshot(row: ConversationControl) -> ControlSnapshot:
    return ControlSnapshot(
        state=ControlState(row.state),
        since=row.since,
        staff_owner=row.staff_owner,
        release_note=row.release_note,
        auto_release_after=row.auto_release_after,
    )


class SqlControlStore:
    def __init__(self, db: ClinicDatabase) -> None:
        self._db = db
        self._care = SqlCareStore(db)

    # ------------------------------------------------------------------------------------ reads
    async def get_control(self, patient_id: UUID) -> ControlSnapshot:
        async with self._db.session() as session:
            row = await session.scalar(
                select(ConversationControl).where(ConversationControl.patient_id == patient_id)
            )
        return ControlSnapshot(ControlState.AUTO) if row is None else _control_snapshot(row)

    async def agent_for_patient(self, patient_id: UUID) -> CareAgentSnapshot | None:
        async with self._db.session() as session:
            row = await session.scalar(select(CareAgent).where(CareAgent.patient_id == patient_id))
            return None if row is None else snapshot_of(row)

    async def get_open_request(self, patient_id: UUID) -> HandoffRequestSnapshot | None:
        async with self._db.session() as session:
            agent = await _agent_row(session, patient_id)
            row = await _open_request(session, patient_id)
            return None if row is None else _request_snapshot(row, agent.id)

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

    # ------------------------------------------------------------------------------ transitions
    async def open_handoff(
        self, agent: CareAgentSnapshot, spec: HandoffSpec, *, log_action: str, at: datetime
    ) -> OpenedHandoff:
        async with self._db.session() as session:
            control = await _locked_control(session, agent.clinic_id, agent.patient_id)
            if control.state != ControlState.AUTO.value:
                existing = await _open_request(session, agent.patient_id) or await _latest_request(
                    session, agent.patient_id
                )
                if existing is None:
                    raise InvalidTransitionError("conversation is not in AUTO and has no handoff request")
                return OpenedHandoff(_request_snapshot(existing, agent.id), created=False)
            request = HandoffRequest(
                clinic_id=agent.clinic_id,
                patient_id=agent.patient_id,
                reason=pack_reason(spec.reason, spec.summary),
                depth=spec.depth,
                confidence=spec.confidence,
                required_skill=spec.required_skill,
                urgency=spec.urgency,
                candidates=[],
            )
            session.add(request)
            control.state = ControlState.HANDOFF_ROUTING.value
            control.since = at
            control.staff_owner = None
            await session.flush()
            self._log(session, agent.clinic_id, agent.id, log_action, spec.depth, at)
            return OpenedHandoff(_request_snapshot(request, agent.id), created=True)

    async def accept(
        self, patient_id: UUID, staff_id: UUID, *, log_action: str, at: datetime
    ) -> HandoffRequestSnapshot:
        async with self._db.session() as session:
            agent = await _agent_row(session, patient_id)
            control = await _locked_control(session, agent.clinic_id, patient_id)
            if control.state != ControlState.HANDOFF_ROUTING.value:
                raise InvalidTransitionError(f"cannot accept from {control.state}")
            request = await _open_request(session, patient_id)
            if request is None:
                raise InvalidTransitionError("no open handoff request")
            request.accepted_by = staff_id
            request.outcome = HandoffOutcome.ACCEPTED.value
            request.resolved_at = at
            control.state = ControlState.STAFF.value
            control.staff_owner = staff_id
            control.since = at
            await session.flush()
            self._log(session, agent.clinic_id, agent.id, log_action, request.depth, at)
            return _request_snapshot(request, agent.id)

    async def record_decline(
        self, patient_id: UUID, staff_id: UUID, *, log_action: str, at: datetime
    ) -> HandoffRequestSnapshot:
        async with self._db.session() as session:
            agent = await _agent_row(session, patient_id)
            control = await _locked_control(session, agent.clinic_id, patient_id)
            if control.state != ControlState.HANDOFF_ROUTING.value:
                raise InvalidTransitionError(f"cannot decline from {control.state}")
            request = await _open_request(session, patient_id)
            if request is None:
                raise InvalidTransitionError("no open handoff request")
            self._log(session, agent.clinic_id, agent.id, log_action, request.depth, at)
            return _request_snapshot(request, agent.id)

    async def release(
        self, patient_id: UUID, staff_id: UUID, spec: ReleaseSpec, *, log_action: str, at: datetime
    ) -> ControlSnapshot:
        async with self._db.session() as session:
            agent = await _agent_row(session, patient_id)
            control = await _locked_control(session, agent.clinic_id, patient_id)
            if control.state != ControlState.STAFF.value:
                raise InvalidTransitionError(f"cannot release from {control.state}")
            control.state = ControlState.AUTO.value
            control.staff_owner = None
            control.release_note = spec.release_note
            control.auto_release_after = None
            control.since = at
            if spec.memory_fact is not None:
                session.add(
                    CareMemory(
                        clinic_id=agent.clinic_id,
                        care_agent_id=agent.id,
                        fact=spec.memory_fact,
                        source=MemorySource.STAFF.value,
                    )
                )
            self._log(session, agent.clinic_id, agent.id, log_action, None, at)
            if spec.override is not None:
                agent.autonomy_override = {
                    "level": level_code(spec.override.level),
                    "until": spec.override.until.isoformat() if spec.override.until else None,
                }
                self._log(
                    session,
                    agent.clinic_id,
                    agent.id,
                    f"autonomy:override_set:level{spec.override.level}",
                    None,
                    at,
                )
            await session.flush()
            return _control_snapshot(control)

    async def set_auto_release_after(
        self, patient_id: UUID, after: timedelta | None, *, log_action: str, at: datetime
    ) -> None:
        async with self._db.session() as session:
            agent = await _agent_row(session, patient_id)
            control = await _locked_control(session, agent.clinic_id, patient_id)
            control.auto_release_after = after
            self._log(session, agent.clinic_id, agent.id, log_action, None, at)

    @staticmethod
    def _log(
        session: AsyncSession,
        clinic_id: UUID,
        care_agent_id: UUID,
        action: str,
        depth: str | None,
        at: datetime,
    ) -> None:
        session.add(
            ActionLog(
                clinic_id=clinic_id,
                care_agent_id=care_agent_id,
                action_type=action,
                depth=depth,
                disposition=ActionDisposition.PAUSED.value,
                at=at,
            )
        )


# ----------------------------------------------------------------------------------------- helpers
async def _agent_row(session: AsyncSession, patient_id: UUID) -> CareAgent:
    row = await session.scalar(select(CareAgent).where(CareAgent.patient_id == patient_id))
    if row is None:
        raise InvalidTransitionError("no care agent for this patient")
    return row


async def _locked_control(session: AsyncSession, clinic_id: UUID, patient_id: UUID) -> ConversationControl:
    await session.execute(
        pg_insert(ConversationControl)
        .values(clinic_id=clinic_id, patient_id=patient_id)
        .on_conflict_do_nothing(index_elements=[ConversationControl.patient_id])
    )
    row = await session.scalar(
        select(ConversationControl)
        .where(ConversationControl.patient_id == patient_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if row is None:  # unreachable: the insert above, or the row that made it conflict, exists
        raise RuntimeError("conversation control row missing right after its insert")
    return row


async def _open_request(session: AsyncSession, patient_id: UUID) -> HandoffRequest | None:
    return await session.scalar(
        select(HandoffRequest)
        .where(HandoffRequest.patient_id == patient_id, HandoffRequest.outcome.is_(None))
        .with_for_update()
    )


async def _latest_request(session: AsyncSession, patient_id: UUID) -> HandoffRequest | None:
    return await session.scalar(
        select(HandoffRequest)
        .where(HandoffRequest.patient_id == patient_id)
        .order_by(HandoffRequest.created_at.desc())
        .limit(1)
    )
