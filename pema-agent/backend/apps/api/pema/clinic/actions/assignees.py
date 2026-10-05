"""Who a task, a conversation or a patient can be handed to (package ST-S). New module, no zalo-agent
original.

Two things live here so that every place that accepts an "assignee" asks the same question:

* ``list_assignable_staff``: the read model behind ``GET /staff/assignable``. ACTIVE staff of the
  installation whose role can work conversations and tasks (``pema.clinic.rbac.ASSIGNABLE_ROLES``), A to Z
  by name, only ``id``, ``name`` and ``role``. Any signed-in staff member may read it (the "Phụ trách" box
  is used by ``cs_staff`` and ``reception`` too, who cannot read ``/admin/users``), so it asks for no
  permission, only for a staff session: the agent, the scheduler and a patient session are refused;
* ``load_assignable_user``: the check every write runs on the user it is about to give work to. The user
  must exist in this installation, be ACTIVE and hold an assignable role (a caller may narrow the roles
  further, for example "doctor" for the patient's treating doctor). An unknown id, a locked account, a role
  that cannot work the item and an id from nowhere all answer the SAME refusal, so the route cannot be
  used to find out which accounts exist or which are locked.

Who may ASSIGN is the permission of each action (``conversation.reply``, ``crm_task.resolve``,
``patient.write``): since ST-S a staff member may hand an item to a colleague, not only to themselves.
Every write puts the previous and the new assignee ids in its audit row (ids only, never a name).
"""

from __future__ import annotations

from collections.abc import Iterable
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pema.clinic.models import UserAccount
from pema.clinic.rbac import ASSIGNABLE_ROLES
from pema.clinic.rbac.authorize import FORBIDDEN_MESSAGE
from pema.core.db import ClinicDatabase
from pema_contracts.actions import ActionContext
from pema_contracts.auth import AssignableStaffOut
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.roles import STAFF_ROLES, ActorType, Role

INVALID_ASSIGNEE_MESSAGE = "Người được giao không hợp lệ."

ASSIGNABLE_ROLE_VALUES: tuple[str, ...] = tuple(sorted(role.value for role in ASSIGNABLE_ROLES))
"""``ASSIGNABLE_ROLES`` as the strings stored in ``clinic.user_account.role``."""


async def list_assignable_staff(db: ClinicDatabase, ctx: ActionContext) -> list[AssignableStaffOut]:
    """Active colleagues that can be assigned work, A to Z by name. Any staff session; nothing else."""
    if ctx.actor_type is not ActorType.USER or ctx.actor_role not in STAFF_ROLES:
        raise DomainError(ErrorCode.FORBIDDEN, FORBIDDEN_MESSAGE)
    async with db.session() as session:
        rows = await session.execute(
            select(UserAccount.id, UserAccount.display_name, UserAccount.role)
            .where(
                UserAccount.clinic_id == ctx.clinic_id,
                UserAccount.active.is_(True),
                UserAccount.role.in_(ASSIGNABLE_ROLE_VALUES),
            )
            .order_by(func.lower(UserAccount.display_name), UserAccount.id)
        )
        return [AssignableStaffOut(id=row.id, name=row.display_name, role=Role(row.role)) for row in rows]


async def load_assignable_user(
    session: AsyncSession,
    ctx: ActionContext,
    user_id: UUID,
    *,
    roles: Iterable[str] = ASSIGNABLE_ROLE_VALUES,
    message: str = INVALID_ASSIGNEE_MESSAGE,
) -> UserAccount:
    """The user of this installation that may receive work, or a 422 ``validation_failed`` with ``message``.

    ``roles`` can only NARROW the assignable roles: a role outside ``ASSIGNABLE_ROLES`` is never
    accepted, even if a caller lists it."""
    allowed = sorted(set(roles) & set(ASSIGNABLE_ROLE_VALUES))
    row = await session.scalar(
        select(UserAccount).where(
            UserAccount.id == user_id,
            UserAccount.clinic_id == ctx.clinic_id,
            UserAccount.active.is_(True),
            UserAccount.role.in_(allowed),
        )
    )
    if row is None:
        raise DomainError(ErrorCode.VALIDATION_FAILED, message)
    return row
