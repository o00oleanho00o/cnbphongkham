"""Staff pickers for every signed-in member (package ST-S): who a task or a conversation can be handed to.

New module. ``GET /staff/assignable`` is NOT under ``/admin``: the "Phụ trách" box of "Việc hôm nay" and the
Inbox header are used by ``cs_staff`` and ``reception`` as well, who cannot read ``/admin/users`` (owner and
manager only, with e-mail, last sign-in and lock state). This route returns the minimum a picker needs and
nothing else. The rule for who is listed (active, assignable role) lives in ``pema.clinic.actions.assignees``,
the same code that every write runs when it accepts an assignee.
"""

from __future__ import annotations

from fastapi import APIRouter, Security

from pema.api import dashboard_auth as auth
from pema.api.deps import ERROR_RESPONSES, cookie_scheme
from pema.api.read_rate_limit import staff_list_limiter
from pema.clinic.actions import assignees
from pema_contracts.auth import AssignableStaffOut
from pema_contracts.errors import DomainError, ErrorCode

router = APIRouter(tags=["staff"], responses=ERROR_RESPONSES, dependencies=[Security(cookie_scheme)])


@router.get(
    "/staff/assignable",
    response_model=list[AssignableStaffOut],
    summary="Colleagues a task or a conversation can be handed to",
    description=(
        "Any signed-in staff member (no admin permission). ACTIVE staff of the clinic whose role can work "
        "conversations and CRM tasks (owner, manager, doctor, cs_staff; not reception), A to Z by name. Only "
        "`id`, `name` and `role`: never an e-mail, a phone, a hash, the last sign-in or a locked account. "
        "Limited to 60 calls per minute per user. The server checks the same rule again when an assignee is "
        "saved, so this list is a convenience, not the authority."
    ),
)
async def list_assignable_staff(db: auth.Database, ctx: auth.Ctx) -> list[AssignableStaffOut]:
    if not staff_list_limiter.allow(f"staff-assignable:{ctx.actor_user_id}"):
        raise DomainError(
            ErrorCode.RATE_LIMITED, "Tải danh sách nhân viên quá nhiều lần. Vui lòng đợi một phút."
        )
    return await assignees.list_assignable_staff(db, ctx)
