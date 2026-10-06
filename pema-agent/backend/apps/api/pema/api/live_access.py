"""What the routes need from the live objects (ST-R): the dependency, the access of a person, the viewers.

New module (not a port). ``app.state.live`` is filled by ``composition.api_wiring.wire_api``; a bare app (the
route tests, the OpenAPI export) has none, and then the stream answers 503 while presence and ``viewers``
quietly do nothing (the Inbox works without them).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request

from pema.api.dashboard_auth import AuthenticatedUser
from pema.clinic.actions import conversations
from pema.clinic.rbac import is_doctor_scoped, permissions_for
from pema.core.db import ClinicDatabase
from pema.live.presence import PresenceEntry
from pema.live.services import LiveServices
from pema.live.sse import StreamAccess
from pema_contracts.actions import ActionContext
from pema_contracts.conversations import ConversationSummary
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.live import LiveEventType, PresenceState, PresenceViewer
from pema_contracts.roles import ActorType, Permission

EVENT_PERMISSION: dict[LiveEventType, Permission] = {
    LiveEventType.INBOX_CHANGED: Permission.CONVERSATION_READ,
    LiveEventType.PRESENCE_CHANGED: Permission.CONVERSATION_READ,
    LiveEventType.ASSIGNMENT_CHANGED: Permission.CONVERSATION_READ,
    LiveEventType.REVIEW_CHANGED: Permission.REVIEW_READ,
    LiveEventType.TASKS_CHANGED: Permission.CRM_TASK_READ,
    LiveEventType.APPOINTMENTS_CHANGED: Permission.APPOINTMENT_READ,
    LiveEventType.HANDOFF_CHANGED: Permission.CARE_READ,
    LiveEventType.CARE_CHANGED: Permission.CARE_READ,
}
"""A person receives an event type only when they may read what it announces."""


def get_live(request: Request) -> LiveServices | None:
    live: object = getattr(request.app.state, "live", None)
    return live if isinstance(live, LiveServices) else None


LiveDep = Annotated[LiveServices | None, Depends(get_live)]


def stream_access_of(user: AuthenticatedUser) -> StreamAccess:
    """Event types by permission; ids only for roles that see the whole clinic (a doctor sees the
    conversations of their own patients, so a doctor's stream names no conversation, task or item)."""
    held = permissions_for(ActorType.USER, user.role)
    types = frozenset(t for t, permission in EVENT_PERMISSION.items() if permission in held)
    return StreamAccess(types=types, with_ids=not is_doctor_scoped(user.action_context()))


async def with_viewers[S: ConversationSummary](
    db: ClinicDatabase, ctx: ActionContext, live: LiveServices | None, items: Sequence[S]
) -> list[S]:
    """Fill ``viewers`` of each conversation: the colleagues who have it open, never the caller and never the
    holder, and ``holder_presence``: whether the holder (package O, step O2) has it open and in which state,
    so the screen can tell "đang trả lời" from "đang xem". One Redis round trip for the whole page and one
    query for the names; a presence store that is down means none."""
    if live is None or not items:
        return list(items)
    present = await live.presence.viewers([item.id for item in items])
    holders = {item.id: item.assigned_user_id for item in items}
    others: dict[UUID, list[PresenceEntry]] = {}
    holder_state: dict[UUID, PresenceState] = {}
    for conversation_id, entries in present.items():
        holder = holders.get(conversation_id)
        others[conversation_id] = [
            e for e in entries if e.user_id != ctx.actor_user_id and e.user_id != holder
        ]
        for entry in entries:
            if holder is not None and entry.user_id == holder:
                holder_state[conversation_id] = entry.state
    user_ids = sorted({e.user_id for entries in others.values() for e in entries}, key=str)
    names = await conversations.staff_display_names(db, ctx, user_ids) if user_ids else {}
    result: list[S] = []
    for item in items:
        viewers = [
            PresenceViewer(user_id=e.user_id, name=names[e.user_id], state=e.state)
            for e in others.get(item.id, [])
            if e.user_id in names
        ]
        update: dict[str, object] = {}
        if viewers:
            update["viewers"] = viewers
        if item.id in holder_state:
            update["holder_presence"] = holder_state[item.id]
        result.append(item.model_copy(update=update) if update else item)
    return result


def actor_id(ctx: ActionContext) -> UUID:
    """The signed-in staff member (presence is per person)."""
    if ctx.actor_user_id is None:  # pragma: no cover - a staff context always has a user
        raise DomainError(ErrorCode.UNAUTHENTICATED, "Bạn chưa đăng nhập.")
    return ctx.actor_user_id
