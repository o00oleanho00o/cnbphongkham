"""Package M's ``StaffNotify`` on the notification outbox (package O, step O3). New module, no zalo-agent
original.

``pema.care.ports.StaffNotify`` is what the routing of package M calls to ask a staff member (or the 24/7
contact) to take a patient. This adapter turns each call into one row of ``clinic.notification_outbox`` with a
PII-free payload (``handoff_payload``: the short code of the request, the depth code, the urgency, the SLA
deadline and a deep link behind the login; NOT the care summary, no patient id), and answers ``True`` once the
row is stored: the delivery chain of ``pema.notify.consumer`` (in-app, push, bell, ...) takes it from there.

* ``notify_staff``: recipient kind ``user``. Nothing else to decide here.
* ``notify_on_call``: recipient kind ``on_call``; the number is NOT stored (package M's rule: it is read from
  the database every time it is used), only the id of the contact row. M keeps its own rule that the on-call
  contact is the last link of every chain. When no internal account is set up the contact cannot be reached at
  all: the adapter answers ``False`` and queues nothing, so M logs ``routing:oncall_notify_failed`` loudly.

Both return ``False`` (never raise) when the row cannot be stored. Logs carry ids and codes only.
"""

from __future__ import annotations

from uuid import UUID

from pema.care.routing_types import HandoffNotice, OnCallInfo
from pema.clinic.actions.notification_chain import internal_account_id
from pema.clinic.actions.notifications import enqueue_handoff_notice, handoff_payload
from pema.core.db import ClinicDatabase, get_installation_clinic_id
from pema.live import emit_live
from pema.shared.logger import create_logger
from pema_contracts.actions import ActionContext, ActionSource
from pema_contracts.live import LiveEventType
from pema_contracts.ops import NotificationRecipientKind
from pema_contracts.roles import ActorType

log = create_logger("notify.staff-notify")


class OutboxStaffNotify:
    """``StaffNotify`` of package M."""

    def __init__(self, db: ClinicDatabase, clinic_id: UUID | None = None) -> None:
        self._db = db
        self._clinic_id = clinic_id

    async def _context(self) -> ActionContext:
        clinic_id = self._clinic_id or await get_installation_clinic_id(self._db)
        return ActionContext(clinic_id=clinic_id, actor_type=ActorType.SYSTEM, source=ActionSource.SYSTEM)

    async def notify_staff(self, user_id: UUID, notice: HandoffNotice) -> bool:
        payload = handoff_payload(
            request_id=notice.request_id,
            urgency=notice.urgency,
            depth=notice.depth,
            position=notice.position,
            sla_due_at=notice.sla_due_at,
            on_call=False,
            to_user_id=user_id,
        )
        return await self._enqueue(payload, NotificationRecipientKind.USER, user_id)

    async def notify_on_call(self, contact: OnCallInfo, notice: HandoffNotice) -> bool:
        ctx = await self._context()
        if await internal_account_id(self._db, ctx.clinic_id) is None:
            log.error(
                "the on-call contact cannot be notified: no internal account",
                request_id=str(notice.request_id),
            )
            return False
        payload = handoff_payload(
            request_id=notice.request_id,
            urgency=notice.urgency,
            depth=notice.depth,
            position=notice.position,
            sla_due_at=notice.sla_due_at,
            on_call=True,
            oncall_id=contact.id,
        )
        return await self._enqueue(payload, NotificationRecipientKind.ON_CALL, None)

    async def _enqueue(
        self, payload: dict[str, object], kind: NotificationRecipientKind, user_id: UUID | None
    ) -> bool:
        try:
            ctx = await self._context()
            async with self._db.session() as session:
                row = await enqueue_handoff_notice(
                    session, ctx, payload=payload, recipient_kind=kind, recipient_user_id=user_id
                )
                notice_id = row.id
        except Exception as err:
            log.error("handoff notice could not be queued", err=err)
            return False
        if user_id is not None:
            emit_live(LiveEventType.NOTIFICATIONS_CHANGED, notice_id)
        return True
