"""Notification outbox and its delivery seam (package O, step O2). New module, no zalo-agent original.

Who is told what happens in the outbox, not on the wire: an assignment change writes one row per recipient
(``clinic.notification_outbox``, state ``pending``) in the SAME transaction as the change, and a later step
(O3) delivers the rows through a ``NotificationDelivery``. Like ``OutboundDelivery`` the seam is a
``Protocol``
here, the real senders (in-app, personal Zalo through the internal notifier, the team group, push) live
outside
``pema.clinic.actions`` and are wired in ``pema.composition``. Nothing in this step delivers anything; step O3
adds the consumer (``pema.notify``), its bookkeeping (``notification_chain.py``) and
``enqueue_handoff_notice`` for package M's ``StaffNotify``.

Recipients of an assignment change (``recipients_of``):

* ``takeover`` and ``shift_end``: the previous holder, the new holder (when there is one) and the team group;
* ``assign``: the previous holder, the new holder and the team group;
* ``claim`` and ``release``: the team group only (nobody else's thread changed hands).

A payload is PII-free by construction: ``NotificationPayload`` (``pema_contracts.ops``) has a fixed set of
fields (``extra = forbid``) and ``serialize_payload`` refuses it when a free-text field carries a phone
number,
an e-mail, an address, a national id, a birth date or a name it was told to look for (the patient and the
customer of the thread). The summary is composed from a template here, never from a message.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from pema.clinic import audit
from pema.clinic.models import NotificationOutbox
from pema.policy.pii import KnownName, mask_pii
from pema_contracts.actions import ActionContext
from pema_contracts.ops import (
    AssignmentKind,
    HandoffNoticeEvent,
    NotificationPayload,
    NotificationRecipientKind,
    NotificationState,
    NotificationUrgency,
)

KIND_PREFIX = "assignment."
CODE_HEX_CHARS = 4
_HANDOFF_ONLY_FIELDS = ("request_id", "position", "sla_due_at", "oncall_id")

_SUMMARIES: Mapping[AssignmentKind, str] = {
    AssignmentKind.CLAIM: "Đã nhận hội thoại {code}",
    AssignmentKind.TAKEOVER: "Hội thoại {code} đã được tiếp quản",
    AssignmentKind.RELEASE: "Hội thoại {code} đã trả về hàng chờ",
    AssignmentKind.SHIFT_END: "Hết ca: hội thoại {code} đổi người phụ trách",
    AssignmentKind.ASSIGN: "Hội thoại {code} đã được giao người phụ trách",
}
_SUMMARY_TO_AGENT = "Hội thoại {code} đã trả lại cho trợ lý"


class UnsafeNotificationPayloadError(ValueError):
    """The payload would carry personal data (a phone number, a name, ...). Nothing is written."""


def short_code(conversation_id: UUID) -> str:
    """The reference operators use in a chat group, "#A1B2": four hex digits of the conversation id. Not
    unique for ever, a pointer for people; the deep link carries the real id."""
    return "#" + conversation_id.hex[:CODE_HEX_CHARS].upper()


def deep_link(conversation_id: UUID) -> str:
    """Opens the conversation in the Inbox; it needs a login."""
    return f"/inbox?conversation={conversation_id}"


def summary_of(kind: AssignmentKind, conversation_id: UUID, *, to_agent: bool = False) -> str:
    template = _SUMMARY_TO_AGENT if kind is AssignmentKind.RELEASE and to_agent else _SUMMARIES[kind]
    return template.format(code=short_code(conversation_id))


def serialize_payload(payload: NotificationPayload, *, forbidden_names: Iterable[str] = ()) -> dict[str, Any]:
    """The JSON stored in the outbox, or ``UnsafeNotificationPayloadError``.

    The free-text fields (``summary``, ``identity_label``) go through the PII mask of ``pema.policy.pii``
    with ``forbidden_names`` (the patient and the customer of the thread) as known names; anything the mask
    would change refuses the payload. The error never repeats the offending text."""
    data = payload.model_dump(mode="json")
    for key in _HANDOFF_ONLY_FIELDS:  # an assignment payload keeps the shape it had in step O2
        if data.get(key) is None:
            data.pop(key, None)
    known = [KnownName(name) for name in forbidden_names if name and name.strip()]
    for key in ("summary", "identity_label"):
        value = data.get(key)
        if isinstance(value, str) and mask_pii(value, known).changed:
            raise UnsafeNotificationPayloadError(f"the notification {key} carries personal data")
    return data


def recipients_of(
    kind: AssignmentKind, *, previous_user_id: UUID | None, new_user_id: UUID | None
) -> list[tuple[NotificationRecipientKind, UUID | None]]:
    """``(recipient kind, user id)`` rows of one change, users first and each user once, the group last."""
    rows: list[tuple[NotificationRecipientKind, UUID | None]] = []
    if kind in (AssignmentKind.TAKEOVER, AssignmentKind.SHIFT_END, AssignmentKind.ASSIGN):
        seen: set[UUID] = set()
        for user_id in (previous_user_id, new_user_id):
            if user_id is not None and user_id not in seen:
                seen.add(user_id)
                rows.append((NotificationRecipientKind.USER, user_id))
    rows.append((NotificationRecipientKind.TEAM_GROUP, None))
    return rows


async def enqueue_assignment_notices(
    session: AsyncSession,
    ctx: ActionContext,
    *,
    conversation_id: UUID,
    kind: AssignmentKind,
    previous_user_id: UUID | None,
    new_user_id: UUID | None,
    identity_label: str | None,
    forbidden_names: Iterable[str] = (),
    to_agent: bool = False,
    urgency: NotificationUrgency = NotificationUrgency.NORMAL,
) -> list[NotificationOutbox]:
    """Write the outbox rows of one assignment change in the caller's transaction (the audit row of the
    change is written by the caller; the guard of ``pema.clinic.audit`` needs it in the same unit of work)."""
    payload = NotificationPayload(
        event=kind,
        short_code=short_code(conversation_id),
        identity_label=identity_label,
        urgency=urgency,
        summary=summary_of(kind, conversation_id, to_agent=to_agent),
        deep_link=deep_link(conversation_id),
        from_user_id=previous_user_id,
        to_user_id=new_user_id,
    )
    data = serialize_payload(payload, forbidden_names=forbidden_names)
    rows = [
        NotificationOutbox(
            clinic_id=ctx.clinic_id,
            kind=KIND_PREFIX + kind.value,
            recipient_kind=recipient_kind.value,
            recipient_user_id=user_id,
            conversation_id=conversation_id,
            payload=data,
            state=NotificationState.PENDING.value,
        )
        for recipient_kind, user_id in recipients_of(
            kind, previous_user_id=previous_user_id, new_user_id=new_user_id
        )
    ]
    session.add_all(rows)
    await session.flush()
    return rows


# ------------------------------------------------------------------------------------- the seam (O3)
@dataclass(frozen=True)
class OutboxNotification:
    """One outbox row as the delivery sees it."""

    id: UUID
    kind: str
    recipient_kind: NotificationRecipientKind
    recipient_user_id: UUID | None
    conversation_id: UUID | None
    payload: Mapping[str, Any]
    attempts: int = 0
    chain_step: str | None = None
    """``None``: the first step of the recipient kind; ``bell``: the in-app step is done, the bell waits."""
    acked: bool = False


@dataclass(frozen=True)
class NotificationResult:
    """``delivered`` False with an ``error_code`` (a short code, never text) is a failed or skipped step; the
    chain of O3 decides what comes next."""

    delivered: bool
    error_code: str | None = None


@runtime_checkable
class NotificationDelivery(Protocol):
    async def deliver(self, ctx: ActionContext, notification: OutboxNotification) -> NotificationResult:
        """Tell the recipient. Does not raise for a refusal of the channel (answer ``delivered=False``)."""
        ...


@dataclass
class FakeNotificationDelivery:
    """Test double: records what it was asked and answers a canned result."""

    result: NotificationResult = field(default_factory=lambda: NotificationResult(delivered=True))
    sent: list[OutboxNotification] = field(default_factory=list[OutboxNotification])
    raises: Exception | None = None

    async def deliver(self, ctx: ActionContext, notification: OutboxNotification) -> NotificationResult:
        self.sent.append(notification)
        if self.raises is not None:
            raise self.raises
        return self.result


# --------------------------------------------------------------------- handoff notices (step O3)
HANDOFF_SUMMARY = "Có yêu cầu chuyển người xử lý {code}"
HANDOFF_ON_CALL_SUMMARY = "Trực 24/7: có yêu cầu chuyển người xử lý {code}"
_URGENT_VALUES = frozenset({"urgent", "critical"})


def handoff_short_code(request_id: UUID) -> str:
    return "#" + request_id.hex[:CODE_HEX_CHARS].upper()


def handoff_deep_link(request_id: UUID) -> str:
    """Opens the handoff request in the care screen; it needs a login."""
    return f"/care/handoffs?request={request_id}"


def handoff_payload(
    *,
    request_id: UUID,
    urgency: str,
    depth: str,
    position: int,
    sla_due_at: Any,
    on_call: bool,
    oncall_id: UUID | None = None,
    to_user_id: UUID | None = None,
) -> dict[str, Any]:
    """The JSON of a handoff notice. The one-line summary is composed here from the short code and the depth
    code (``D1`` .. ``D5``); the care summary of package M is NOT copied (the deep link opens it behind the
    login), so nothing of the patient can reach a chat. The payload check still runs; if it ever refuses the
    depth text the sentence without it is used: a handoff notice is never dropped over its wording."""
    code = handoff_short_code(request_id)
    generic = (HANDOFF_ON_CALL_SUMMARY if on_call else HANDOFF_SUMMARY).format(code=code)

    def build(text: str) -> NotificationPayload:
        return NotificationPayload(
            event=HandoffNoticeEvent.HANDOFF_ON_CALL if on_call else HandoffNoticeEvent.HANDOFF_REQUEST,
            short_code=code,
            urgency=NotificationUrgency.URGENT if urgency in _URGENT_VALUES else NotificationUrgency.NORMAL,
            summary=text,
            deep_link=handoff_deep_link(request_id),
            to_user_id=to_user_id,
            request_id=request_id,
            position=position,
            sla_due_at=sla_due_at,
            oncall_id=oncall_id,
        )

    try:
        return serialize_payload(build(f"{generic} · {depth[:8]}"))
    except UnsafeNotificationPayloadError:
        return serialize_payload(build(generic))


async def enqueue_handoff_notice(
    session: AsyncSession,
    ctx: ActionContext,
    *,
    payload: Mapping[str, Any],
    recipient_kind: NotificationRecipientKind,
    recipient_user_id: UUID | None,
) -> NotificationOutbox:
    """One outbox row for a notice of package M's routing, with its audit row (ids and codes only)."""
    row = NotificationOutbox(
        clinic_id=ctx.clinic_id,
        kind="handoff." + str(payload["event"]),
        recipient_kind=recipient_kind.value,
        recipient_user_id=recipient_user_id,
        conversation_id=None,
        payload=dict(payload),
        state=NotificationState.PENDING.value,
    )
    session.add(row)
    await session.flush()
    await audit.record(
        session,
        ctx,
        "notification.enqueue",
        "notification",
        row.id,
        {
            "kind": row.kind,
            "recipient_kind": recipient_kind.value,
            "recipient_user_id": str(recipient_user_id) if recipient_user_id else None,
        },
    )
    return row
