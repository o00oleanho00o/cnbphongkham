"""Wiring of the notification chain (package O, step O3). New module, no zalo-agent original.

``build_notify_stack`` assembles, from the ``Runtime`` of the API process (role ``be_app``):

* the SQL stores over ``pema.clinic.actions`` and the internal Zalo sender (it writes through
  ``rt.channels``, the registry of the running accounts, with ``channel.send_text``; the per-identity send
  queue
  of O4 passes internal accounts through unpaced);
* the ``NotificationConsumer`` (in-app, push, bell, team group, on-call), a loop that runs every
  ``interval_s`` seconds in the API process like the CRM rule runner (the outbox lives in ``clinic.*``, which
  only ``be_app`` reads);
* the production adapters of package M: ``OutboxStaffNotify`` (``StaffNotify``) and ``DurableSlaScheduler``
  (``SlaScheduler``), for the care wiring of package M7 to pick up from ``stack.staff_notify`` and
  ``stack.sla_scheduler``;
* the ``SlaCheckRunner``, started only when a handler is given (``RoutingService.on_sla_expired``; M7 passes
  it, until then the checks wait in ``clinic.sla_check`` and M's ``sweep_overdue`` is the backstop);
* the link handler of the internal account, registered in ``rt.internal``.

``bind_internal_registry`` is used by the intake wiring (both processes): it points ``rt.internal`` at the
database so the intake path knows which accounts are internal (never a customer conversation, never a turn).

Push: ``FakePushProvider`` is not wired here. Without a provider the push step is skipped and logged
(``provider_disabled``); the real ``FcmApnsPushProvider`` is a disabled skeleton until credentials and the KMP
client exist.
"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
from uuid import UUID

from pema.clinic.actions import notification_chain
from pema.composition.runtime import Runtime
from pema.core.db import get_installation_clinic_id
from pema.notify.consumer import NotificationConsumer
from pema.notify.internal import InternalZaloSender
from pema.notify.link import InternalAccountRegistry, LinkHandler
from pema.notify.providers import (
    InAppProvider,
    OnCallBellProvider,
    PushProvider,
    TeamGroupProvider,
    ZaloBellProvider,
)
from pema.notify.sla import DurableSlaScheduler, SlaCheckRunner, SlaExpiryHandler
from pema.notify.staff_notify import OutboxStaffNotify
from pema.notify.store import SqlNotifyStore, SqlSlaStore
from pema.shared.logger import create_logger
from pema_contracts.channel import InboundMessage

log = create_logger("composition.notify")

DEFAULT_INTERVAL_S = 5.0


def bind_internal_registry(rt: Runtime) -> InternalAccountRegistry:
    """Make ``rt.internal`` read the internal accounts from this process's database (idempotent)."""
    registry = rt.internal
    if registry.loader is None:

        async def load() -> frozenset[str]:
            clinic_id = await get_installation_clinic_id(rt.db)
            return await notification_chain.list_internal_account_ids(rt.db, clinic_id)

        registry.loader = load
    return registry


@dataclass
class NotifyStack:
    clinic_id: UUID
    store: SqlNotifyStore
    consumer: NotificationConsumer
    staff_notify: OutboxStaffNotify
    sla_scheduler: DurableSlaScheduler
    sla_runner: SlaCheckRunner | None
    link_handler: LinkHandler
    interval_s: float = DEFAULT_INTERVAL_S
    _task: asyncio.Task[None] | None = None

    async def run_once(self) -> None:
        await self.consumer.run_once()
        if self.sla_runner is not None:
            await self.sla_runner.run_once()

    async def _loop(self) -> None:
        while True:
            try:
                await self.run_once()
            except Exception as err:
                log.error("notification loop failed", err=err)
            await asyncio.sleep(self.interval_s)

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.get_running_loop().create_task(self._loop())

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task


async def build_notify_stack(
    rt: Runtime,
    *,
    push: PushProvider | None = None,
    sla_handler: SlaExpiryHandler | None = None,
    interval_s: float = DEFAULT_INTERVAL_S,
) -> NotifyStack:
    clinic_id = await get_installation_clinic_id(rt.db)
    store = SqlNotifyStore(rt.db, clinic_id)
    sla_store = SqlSlaStore(rt.db, clinic_id)
    sender = InternalZaloSender(clinic_id, rt.channels, store)
    consumer = NotificationConsumer(
        store=store,
        in_app=InAppProvider(),
        bell=ZaloBellProvider(sender),
        group=TeamGroupProvider(sender),
        on_call=OnCallBellProvider(sender),
        push=push,
    )
    link_handler = LinkHandler(store, sender)

    registry = bind_internal_registry(rt)

    async def on_internal_message(_clinic_id: UUID, message: InboundMessage) -> None:
        await link_handler.handle(message)

    registry.handler = on_internal_message
    return NotifyStack(
        clinic_id=clinic_id,
        store=store,
        consumer=consumer,
        staff_notify=OutboxStaffNotify(rt.db, clinic_id),
        sla_scheduler=DurableSlaScheduler(sla_store),
        sla_runner=SlaCheckRunner(sla_store, sla_handler) if sla_handler is not None else None,
        link_handler=link_handler,
        interval_s=interval_s,
    )
