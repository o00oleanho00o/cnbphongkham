"""Who holds a conversation: claim, takeover, release, assign, end of shift, history (package O, step O2).
New module, no zalo-agent original.

The holder of a thread is ``clinic.conversation.assigned_user_id`` (unchanged: the "Phụ trách" box and
``GET /staff/assignable`` keep working). This module adds the rules around it: exactly one operator replies in
a thread at a time, the others can read, takeover is allowed and both operators are told, release hands the
thread back. Everything that changes a holder runs through ``_assignment_core.apply_assignment``: history row,
audit row, outbox rows (``notifications.py``), ``assignment_version`` bump, all in one transaction, with the
conversation loaded ``FOR UPDATE`` so concurrent changes of one thread run one after the other.

Rules, by action:

* ``claim`` (``thread.claim``, every assignable role): only an unassigned thread (the holder released it, or
  nobody ever held it). A thread somebody else holds answers 409 ``thread_locked`` with the holder's name.
  Claiming a thread one already holds changes nothing.
* ``takeover`` (``thread.claim``): the thread has a holder who is somebody else; a reason is required and is
  kept in the history (never in the audit row or a notification). Previous and new holder and the team group
  get a notice.
* ``release`` (``thread.claim``): the holder gives the thread back (an owner or manager, ``thread.assign``,
  may
  release any thread). To the queue, or with ``to_agent`` to the care agent of package M: the patient must be
  in M's STAFF state and ``CareHandback.release_to_auto`` is called in the same unit of work, after the local
  change was flushed, so a refusal of M leaves the thread as it was. M is the safety owner of that state: it
  is never released implicitly.
* ``assign`` (``thread.assign``, owner and manager): put an assignable colleague on the thread whoever holds
  it, or take it off (``user_id`` null).
* ``end_shift`` (``thread.end_shift``, owner and manager): every active (not closed) thread of the user moves
  to an operator who is on duty for the thread's identity (``roster.who_is_on``; the one with the fewest
  active
  threads, A to Z on a tie), else back to the queue. One transaction per thread: a thread that changed
  hands in
  the meantime is skipped, a failure of one thread does not undo the others. A message that is queued or being
  sent finishes (it passed the send lock before); the old holder's next send is refused.

Live: ``assignment.changed`` and ``inbox.changed`` after each commit.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from pema.clinic.actions._assignment_core import (
    acting_user_id,
    apply_assignment,
    check_assignment_version,
    locked_error,
)
from pema.clinic.actions._common import now
from pema.clinic.actions.assignees import load_assignable_user
from pema.clinic.actions.conversations import conversation_detail, load_conversation
from pema.clinic.actions.roster import who_is_on
from pema.clinic.models import Conversation, ConversationAssignment, UserAccount
from pema.clinic.rbac import has_permission, require
from pema.core.db import ClinicDatabase
from pema.live import emit_live
from pema_contracts.actions import ActionContext
from pema_contracts.conversations import ConversationOut, ConversationStatus
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.live import LiveEventType
from pema_contracts.ops import (
    AssignmentEventOut,
    AssignmentKind,
    AssignRequest,
    ClaimRequest,
    EndShiftResult,
    ReleaseRequest,
    TakeoverRequest,
)
from pema_contracts.roles import Permission

NOBODY_HOLDS_MESSAGE = "Hội thoại chưa có người phụ trách. Hãy bấm Nhận."
ALREADY_YOURS_MESSAGE = "Bạn đang phụ trách hội thoại này."
NO_PATIENT_MESSAGE = "Hội thoại chưa gắn với bệnh nhân nên không trả lại cho trợ lý được."
NO_CARE_MESSAGE = "Chưa nối với trợ lý chăm sóc nên chưa trả lại cho trợ lý được."
NOT_STAFF_STATE_MESSAGE = "Bệnh nhân không ở trạng thái nhân viên đang xử lý, chưa thể trả lại cho trợ lý."
UNKNOWN_STAFF_MESSAGE = "Không tìm thấy nhân viên."

# ``Conversation.status`` values that are not "active" for the end of a shift
_CLOSED = ConversationStatus.CLOSED.value


class CareHandbackRefusedError(Exception):
    """Package M refused the hand-back (the patient is not in its STAFF state, or a rule of its own)."""


@runtime_checkable
class CareHandback(Protocol):
    """The seam to package M's ``CareControl`` (``release_to_auto`` is keyed by PATIENT, not conversation).
    ``pema.composition.care_assignment`` adapts the real one; tests use a fake."""

    async def is_staff_state(self, ctx: ActionContext, patient_id: UUID) -> bool:
        """The patient's conversation is in M's STAFF state (a person has it; the agent only suggests)."""
        ...

    async def release_to_auto(self, ctx: ActionContext, patient_id: UUID, note: str) -> None:
        """M's ``STAFF -> AUTO``. Raises ``CareHandbackRefusedError`` when M refuses."""
        ...


# --------------------------------------------------------------------------------------------- claim
async def claim(
    db: ClinicDatabase, ctx: ActionContext, conversation_id: UUID, request: ClaimRequest | None = None
) -> ConversationOut:
    require(ctx, Permission.THREAD_CLAIM)
    me = acting_user_id(ctx)
    changed = False
    async with db.session() as session:
        conv = await load_conversation(session, ctx, conversation_id, for_update=True)
        if conv.assigned_user_id == me:
            return await conversation_detail(session, ctx, conversation_id)
        if conv.assigned_user_id is not None:
            raise await locked_error(session, ctx, conv)
        check_assignment_version(conv, request.assignment_version if request else None)
        await apply_assignment(session, ctx, conv, kind=AssignmentKind.CLAIM, new_user_id=me)
        changed = True
        result = await conversation_detail(session, ctx, conversation_id)
    _announce(conversation_id, changed)
    return result


# ----------------------------------------------------------------------------------------- takeover
async def takeover(
    db: ClinicDatabase, ctx: ActionContext, conversation_id: UUID, request: TakeoverRequest
) -> ConversationOut:
    require(ctx, Permission.THREAD_CLAIM)
    me = acting_user_id(ctx)
    async with db.session() as session:
        conv = await load_conversation(session, ctx, conversation_id, for_update=True)
        if conv.assigned_user_id == me:
            raise DomainError(ErrorCode.INVALID_STATE, ALREADY_YOURS_MESSAGE)
        if conv.assigned_user_id is None:
            raise DomainError(ErrorCode.INVALID_STATE, NOBODY_HOLDS_MESSAGE)
        check_assignment_version(conv, request.assignment_version)
        await apply_assignment(
            session, ctx, conv, kind=AssignmentKind.TAKEOVER, new_user_id=me, reason=request.reason
        )
        result = await conversation_detail(session, ctx, conversation_id)
    _announce(conversation_id, True)
    return result


# ------------------------------------------------------------------------------------------ release
async def release(
    db: ClinicDatabase,
    ctx: ActionContext,
    conversation_id: UUID,
    request: ReleaseRequest | None = None,
    *,
    care: CareHandback | None = None,
) -> ConversationOut:
    require(ctx, Permission.THREAD_CLAIM)
    me = acting_user_id(ctx)
    body = request or ReleaseRequest()
    changed = False
    async with db.session() as session:
        conv = await load_conversation(session, ctx, conversation_id, for_update=True)
        if conv.assigned_user_id is None:
            return await conversation_detail(session, ctx, conversation_id)
        if conv.assigned_user_id != me and not has_permission(ctx, Permission.THREAD_ASSIGN):
            raise await locked_error(session, ctx, conv)
        check_assignment_version(conv, body.assignment_version)
        patient_id = conv.patient_id
        if body.to_agent:
            if patient_id is None:
                raise DomainError(ErrorCode.INVALID_STATE, NO_PATIENT_MESSAGE)
            if care is None:
                raise DomainError(ErrorCode.NOT_IMPLEMENTED, NO_CARE_MESSAGE)
            if not await care.is_staff_state(ctx, patient_id):
                raise DomainError(ErrorCode.INVALID_STATE, NOT_STAFF_STATE_MESSAGE)
        await apply_assignment(
            session,
            ctx,
            conv,
            kind=AssignmentKind.RELEASE,
            new_user_id=None,
            reason=body.note,
            to_agent=body.to_agent,
        )
        changed = True
        if body.to_agent and care is not None and patient_id is not None:
            try:
                await care.release_to_auto(ctx, patient_id, body.note or "")
            except CareHandbackRefusedError as exc:  # rolls back the local release as well
                raise DomainError(ErrorCode.INVALID_STATE, NOT_STAFF_STATE_MESSAGE) from exc
        result = await conversation_detail(session, ctx, conversation_id)
    _announce(conversation_id, changed)
    return result


# -------------------------------------------------------------------------------------------- assign
async def assign(
    db: ClinicDatabase, ctx: ActionContext, conversation_id: UUID, request: AssignRequest
) -> ConversationOut:
    require(ctx, Permission.THREAD_ASSIGN)
    acting_user_id(ctx)
    changed = False
    async with db.session() as session:
        conv = await load_conversation(session, ctx, conversation_id, for_update=True)
        check_assignment_version(conv, request.assignment_version)
        if request.user_id is not None:
            await load_assignable_user(session, ctx, request.user_id)
        if request.user_id != conv.assigned_user_id:
            await apply_assignment(
                session, ctx, conv, kind=AssignmentKind.ASSIGN, new_user_id=request.user_id
            )
            changed = True
        result = await conversation_detail(session, ctx, conversation_id)
    _announce(conversation_id, changed)
    return result


# ----------------------------------------------------------------------------------------- end shift
async def end_shift(db: ClinicDatabase, ctx: ActionContext, user_id: UUID) -> EndShiftResult:
    """Move the active threads of ``user_id`` to whoever is on duty, else back to the queue."""
    require(ctx, Permission.THREAD_END_SHIFT)
    acting_user_id(ctx)
    async with db.session() as session:
        known = await session.scalar(
            select(UserAccount.id).where(UserAccount.id == user_id, UserAccount.clinic_id == ctx.clinic_id)
        )
        if known is None:
            raise DomainError(ErrorCode.NOT_FOUND, UNKNOWN_STAFF_MESSAGE)
        threads = (
            await session.execute(
                text(
                    "SELECT c.id, c.account_id FROM clinic.conversation c "
                    "WHERE c.clinic_id = :clinic_id AND c.assigned_user_id = :user_id "
                    "AND c.status <> :closed "
                    "ORDER BY c.last_message_at DESC NULLS LAST, c.id"
                ),
                {"clinic_id": ctx.clinic_id, "user_id": user_id, "closed": _CLOSED},
            )
        ).all()
        load = await _active_thread_counts(session, ctx)

    moment = now()
    on_duty: dict[str, list[UUID]] = {}
    rerouted = to_queue = skipped = 0
    for thread_id, account_id in threads:
        target: UUID | None = None
        if account_id is not None:
            if account_id not in on_duty:  # one roster lookup per identity, not per thread
                operators = await who_is_on(db, ctx.clinic_id, str(account_id), moment)
                on_duty[account_id] = [op.id for op in operators if op.id != user_id]
            candidates = on_duty[account_id]
            if candidates:  # who_is_on is A to Z: min() keeps the first of equals
                target = min(candidates, key=lambda candidate: load.get(candidate, 0))
        async with db.session() as session:
            conv = await load_conversation(session, ctx, thread_id, for_update=True)
            if conv.assigned_user_id != user_id or conv.status == _CLOSED:
                skipped += 1
                continue
            await apply_assignment(session, ctx, conv, kind=AssignmentKind.SHIFT_END, new_user_id=target)
        _announce(thread_id, True)
        if target is None:
            to_queue += 1
        else:
            rerouted += 1
            load[target] = load.get(target, 0) + 1
    return EndShiftResult(user_id=user_id, rerouted=rerouted, to_queue=to_queue, skipped=skipped)


async def _active_thread_counts(session: AsyncSession, ctx: ActionContext) -> dict[UUID, int]:
    """Active threads per holder, one query for the whole run (the balance of ``end_shift``)."""
    rows = await session.execute(
        text(
            "SELECT assigned_user_id, count(*) FROM clinic.conversation "
            "WHERE clinic_id = :clinic_id AND assigned_user_id IS NOT NULL AND status <> :closed "
            "GROUP BY assigned_user_id"
        ),
        {"clinic_id": ctx.clinic_id, "closed": _CLOSED},
    )
    return {row[0]: int(row[1]) for row in rows.all()}


# ---------------------------------------------------------------------------------------------- history
async def list_assignments(
    db: ClinicDatabase, ctx: ActionContext, conversation_id: UUID
) -> list[AssignmentEventOut]:
    """The history of one conversation, newest first. Whoever may read the conversation may read it."""
    require(ctx, Permission.CONVERSATION_READ)
    async with db.session() as session:
        await load_conversation(session, ctx, conversation_id)
        rows = (
            await session.scalars(
                select(ConversationAssignment)
                .where(
                    ConversationAssignment.clinic_id == ctx.clinic_id,
                    ConversationAssignment.conversation_id == conversation_id,
                )
                .order_by(ConversationAssignment.at.desc(), ConversationAssignment.id)
            )
        ).all()
        user_ids = {uid for row in rows for uid in (row.user_id, row.previous_user_id) if uid is not None}
        names: dict[UUID, str] = {}
        if user_ids:
            named = await session.execute(
                select(UserAccount.id, UserAccount.display_name).where(
                    UserAccount.clinic_id == ctx.clinic_id, UserAccount.id.in_(user_ids)
                )
            )
            names = {row.id: row.display_name for row in named.all()}
    return [
        AssignmentEventOut(
            id=row.id,
            kind=AssignmentKind(row.kind),
            user_id=row.user_id,
            user_name=names.get(row.user_id) if row.user_id else None,
            previous_user_id=row.previous_user_id,
            previous_user_name=names.get(row.previous_user_id) if row.previous_user_id else None,
            reason=row.reason,
            at=row.at,
            by=row.by,
        )
        for row in rows
    ]


# ------------------------------------------------------------------------- the bridge to package M
async def open_conversation_of_patient(db: ClinicDatabase, clinic_id: UUID, patient_id: UUID) -> UUID | None:
    """The open (not closed) conversation of a patient with the LATEST inbound message: package M works per
    patient, a thread is per customer and identity, and a patient may have several. ``None`` when there is
    none. No permission: the lookup of the care bridge (``pema.composition.care_assignment``)."""
    async with db.session() as session:
        return await session.scalar(
            select(Conversation.id)
            .where(
                Conversation.clinic_id == clinic_id,
                Conversation.patient_id == patient_id,
                Conversation.status != _CLOSED,
            )
            .order_by(Conversation.last_inbound_at.desc().nulls_last(), Conversation.id)
            .limit(1)
        )


async def claim_for_patient(
    db: ClinicDatabase, ctx: ActionContext, patient_id: UUID
) -> ConversationOut | None:
    """M's ``accept`` as a claim: the staff member who accepted the handoff takes the patient's open
    conversation with the latest inbound message. ``None`` when the patient has no open conversation."""
    conversation_id = await open_conversation_of_patient(db, ctx.clinic_id, patient_id)
    if conversation_id is None:
        return None
    return await claim(db, ctx, conversation_id)


async def release_for_patient(
    db: ClinicDatabase, ctx: ActionContext, patient_id: UUID, *, note: str | None = None
) -> ConversationOut | None:
    """M's release as a release of the thread (back to the queue): the conversation the staff member holds,
    the one with the latest inbound message. ``None`` when there is none or somebody else holds it."""
    conversation_id = await open_conversation_of_patient(db, ctx.clinic_id, patient_id)
    if conversation_id is None:
        return None
    try:
        return await release(db, ctx, conversation_id, ReleaseRequest(note=note))
    except DomainError as exc:
        if exc.code is ErrorCode.THREAD_LOCKED:
            return None
        raise


def _announce(conversation_id: UUID, changed: bool) -> None:
    if changed:
        emit_live(LiveEventType.ASSIGNMENT_CHANGED, conversation_id)
        emit_live(LiveEventType.INBOX_CHANGED, conversation_id)


__all__ = [
    "CareHandback",
    "CareHandbackRefusedError",
    "assign",
    "claim",
    "claim_for_patient",
    "end_shift",
    "list_assignments",
    "open_conversation_of_patient",
    "release",
    "release_for_patient",
    "takeover",
]
