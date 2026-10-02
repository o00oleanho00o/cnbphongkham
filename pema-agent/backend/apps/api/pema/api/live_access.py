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
from pema.live.services import LiveServices
from pema.live.sse import StreamAccess
from pema_contracts.actions import ActionContext
from pema_contracts.conversations import ConversationSummary
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.live import LiveEventType, PresenceViewer
from pema_contracts.roles import ActorType, Permission

EVENT_PERMISSION: dict[LiveEventType, Permission] = {
    LiveEventType.INBOX_CHANGED: Permission.CONVERSATION_READ,
    LiveEventType.PRESENCE_CHANGED: Permission.CONVERSATION_READ,
    LiveEventType.REVIEW_CHANGED: Permission.REVIEW_READ,
    LiveEventType.TASKS_CHANGED: Permission.CRM_TASK_READ,
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
    """Fill ``viewers`` of each conversation: the colleagues who have it open, never the caller. One Redis
    round trip for the whole page and one query for the names; a presence store that is down means none."""
    if live is None or not items:
        return list(items)
    present = await live.presence.viewers([item.id for item in items])
    others = {
        conversation_id: [e for e in entries if e.user_id != ctx.actor_user_id]
        for conversation_id, entries in present.items()
    }
    user_ids = sorted({e.user_id for entries in others.values() for e in entries}, key=str)
    if not user_ids:
        return list(items)
    names = await conversations.staff_display_names(db, ctx, user_ids)
    result: list[S] = []
    for item in items:
        viewers = [
            PresenceViewer(user_id=e.user_id, name=names[e.user_id], state=e.state)
            for e in others.get(item.id, [])
            if e.user_id in names
        ]
        result.append(item.model_copy(update={"viewers": viewers}) if viewers else item)
    return result


def actor_id(ctx: ActionContext) -> UUID:
    """The signed-in staff member (presence is per person)."""
    if ctx.actor_user_id is None:  # pragma: no cover - a staff context always has a user
        raise DomainError(ErrorCode.UNAUTHENTICATED, "Bạn chưa đăng nhập.")
    return ctx.actor_user_id
