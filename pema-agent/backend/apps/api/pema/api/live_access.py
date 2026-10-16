"""What the routes need from the live objects (ST-R): the dependency and the access of a person.

New module (not a port). ``app.state.live`` is filled by ``composition.api_wiring.wire_api``; a bare app (the
route tests, the OpenAPI export) has none, and then the stream answers 503.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from pema.api.dashboard_auth import AuthenticatedUser
from pema.clinic.rbac import is_doctor_scoped, permissions_for
from pema.live.services import LiveServices
from pema.live.sse import StreamAccess
from pema_contracts.live import LiveEventType
from pema_contracts.roles import ActorType, Permission

EVENT_PERMISSION: dict[LiveEventType, Permission] = {
    LiveEventType.TASKS_CHANGED: Permission.CRM_TASK_READ,
    LiveEventType.APPOINTMENTS_CHANGED: Permission.APPOINTMENT_READ,
}
"""A person receives an event type only when they may read what it announces."""


def get_live(request: Request) -> LiveServices | None:
    live: object = getattr(request.app.state, "live", None)
    return live if isinstance(live, LiveServices) else None


LiveDep = Annotated[LiveServices | None, Depends(get_live)]


def stream_access_of(user: AuthenticatedUser) -> StreamAccess:
    """Event types by permission; ids only for roles that see the whole clinic (a doctor sees their own
    patients only, so a doctor's stream names no task or appointment)."""
    held = permissions_for(ActorType.USER, user.role)
    types = frozenset(t for t, permission in EVENT_PERMISSION.items() if permission in held)
    return StreamAccess(types=types, with_ids=not is_doctor_scoped(user.action_context()))
