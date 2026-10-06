"""The session-level core of the assignment actions (package O, step O2). New module, no zalo-agent original.

Private to ``pema.clinic.actions``: ``assignment.py`` (the public actions) and ``conversations.py`` (the send
lock and the "Phụ trách" update) both build on it, so it imports neither of them.

One conversation has at most one holder because the holder is ONE column, ``conversation.assigned_user_id``.
Every change of it goes through ``apply_assignment``, which in the caller's transaction

* sets the new holder and bumps ``assignment_version``,
* appends a row to ``clinic.conversation_assignment`` (the history),
* writes the audit row (ids and kind only: never the reason, a name or a message),
* writes the outbox rows of the notification (``notifications.py``).

Callers load the conversation ``FOR UPDATE`` first, so two changes of the same thread run one after the other
and the second one sees the first one's result (a second claim finds a holder and answers ``thread_locked``;
a send that already started finishes before a takeover is applied). The caller emits the live events after the
commit.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from pema.clinic import audit
from pema.clinic.actions._common import check_version, lost_race_is_conflict
from pema.clinic.actions.notifications import enqueue_assignment_notices
from pema.clinic.models import ChannelIdentity, Conversation, ConversationAssignment, Patient, UserAccount
from pema_contracts.actions import ActionContext
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.ops import AssignmentKind

LOCKED_MESSAGE = "{name} đang trả lời — Tiếp quản?"
UNKNOWN_HOLDER_NAME = "Đồng nghiệp"
NO_STAFF_MESSAGE = "Chỉ nhân viên đã đăng nhập mới nhận hoặc giao hội thoại."


def acting_user_id(ctx: ActionContext) -> UUID:
    """The staff member who acts; the agent, the scheduler and the system hold no thread."""
    if ctx.actor_user_id is None:
        raise DomainError(ErrorCode.FORBIDDEN, NO_STAFF_MESSAGE)
    return ctx.actor_user_id


async def holder_display_name(session: AsyncSession, ctx: ActionContext, user_id: UUID | None) -> str | None:
    if user_id is None:
        return None
    return await session.scalar(
        select(UserAccount.display_name).where(
            UserAccount.id == user_id, UserAccount.clinic_id == ctx.clinic_id
        )
    )


async def locked_error(session: AsyncSession, ctx: ActionContext, conv: Conversation) -> DomainError:
    """409 ``thread_locked`` with the holder's name: "<Tên> đang trả lời — Tiếp quản?". The details carry the
    holder id and the ``assignment_version`` a takeover can send back."""
    name = await holder_display_name(session, ctx, conv.assigned_user_id) or UNKNOWN_HOLDER_NAME
    return DomainError(
        ErrorCode.THREAD_LOCKED,
        LOCKED_MESSAGE.format(name=name),
        details={
            "holder_user_id": str(conv.assigned_user_id) if conv.assigned_user_id else None,
            "assignment_version": conv.assignment_version,
        },
    )


def check_assignment_version(conv: Conversation, expected: int | None) -> None:
    """The client saw ``expected``; ``None`` means "whatever is stored" (the caller holds the row lock)."""
    if expected is not None:
        check_version(conv.assignment_version, expected)


async def _notice_context(
    session: AsyncSession, ctx: ActionContext, conv: Conversation
) -> tuple[str | None, list[str]]:
    """The identity label to show and the names a notification must never carry (the patient and the
    customer of the thread). Three small reads of the one conversation."""
    label = await session.scalar(
        text(
            "SELECT a.label FROM clinic.conversation c "
            "JOIN agent.accounts a ON a.clinic_id = c.clinic_id AND a.id = c.account_id "
            "WHERE c.clinic_id = :clinic_id AND c.id = :conversation_id"
        ),
        {"clinic_id": ctx.clinic_id, "conversation_id": conv.id},
    )
    names: list[str] = []
    if conv.patient_id is not None:
        patient_name = await session.scalar(
            select(Patient.full_name).where(Patient.id == conv.patient_id, Patient.clinic_id == ctx.clinic_id)
        )
        if patient_name:
            names.append(patient_name)
    if conv.identity_id is not None:
        customer_name = await session.scalar(
            select(ChannelIdentity.display_name).where(
                ChannelIdentity.id == conv.identity_id, ChannelIdentity.clinic_id == ctx.clinic_id
            )
        )
        if customer_name:
            names.append(customer_name)
    return label, names


async def apply_assignment(
    session: AsyncSession,
    ctx: ActionContext,
    conv: Conversation,
    *,
    kind: AssignmentKind,
    new_user_id: UUID | None,
    reason: str | None = None,
    to_agent: bool = False,
) -> ConversationAssignment:
    """Change the holder of ``conv`` (loaded ``FOR UPDATE`` by the caller) and write everything that goes
    with it. A lost optimistic race (``StaleDataError``) is a 409 ``version_conflict``."""
    previous = conv.assigned_user_id
    conv.assigned_user_id = new_user_id
    conv.assignment_version += 1
    history = ConversationAssignment(
        clinic_id=ctx.clinic_id,
        conversation_id=conv.id,
        user_id=new_user_id,
        kind=kind.value,
        previous_user_id=previous,
        reason=reason,
        by=ctx.actor_user_id,
    )
    session.add(history)
    with lost_race_is_conflict():
        await session.flush()
    await audit.record(
        session,
        ctx,
        f"thread.{kind.value}",
        "conversation",
        conv.id,
        {
            "kind": kind.value,
            "previous_user_id": str(previous) if previous else None,
            "user_id": str(new_user_id) if new_user_id else None,
            "has_reason": reason is not None,
            "to_agent": to_agent,
            "assignment_version": conv.assignment_version,
        },
    )
    label, forbidden = await _notice_context(session, ctx, conv)
    await enqueue_assignment_notices(
        session,
        ctx,
        conversation_id=conv.id,
        kind=kind,
        previous_user_id=previous,
        new_user_id=new_user_id,
        identity_label=label,
        forbidden_names=forbidden,
        to_agent=to_agent,
    )
    return history


async def enforce_reply_lock(session: AsyncSession, ctx: ActionContext, conv: Conversation) -> bool:
    """The send lock: only the holder replies. Returns True when this call claimed an unassigned thread (the
    first reply of an operator is a claim), False when the caller already holds it; raises ``thread_locked``
    when somebody else holds it. A call without a staff member behind it (the system) is not an operator and
    is not locked."""
    if ctx.actor_user_id is None:
        return False
    holder = conv.assigned_user_id
    if holder == ctx.actor_user_id:
        return False
    if holder is not None:
        raise await locked_error(session, ctx, conv)
    await apply_assignment(session, ctx, conv, kind=AssignmentKind.CLAIM, new_user_id=ctx.actor_user_id)
    return True
