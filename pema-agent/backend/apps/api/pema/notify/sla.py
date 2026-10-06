"""Package M's ``SlaScheduler`` on durable checks (package O, step O3). New module, no zalo-agent original.

``DurableSlaScheduler.schedule_check`` stores "look at routing request R again at T" in ``clinic.sla_check``
(deduplicated by M's ``dedupe_key``, so a repeat is harmless). ``SlaCheckRunner.run_once`` takes the checks
that
are due (a lease, ``FOR UPDATE SKIP LOCKED``) and calls ``SlaExpiryHandler.on_sla_expired(request_id, idx)``,
which is ``pema.care.routing.RoutingService.on_sla_expired``: the current candidate did not accept or decline
in time, so the chain moves to the next candidate and, last, the 24/7 contact.

"Never sent, never ran": a check is marked ``done`` only AFTER its handler returned. A handler that raises
leaves the check pending for a later retry (growing delay, at most ``MAX_ATTEMPTS`` times, then ``failed`` and
an error in the log); M's own ``sweep_overdue`` stays the backstop for a request whose check never ran.

Deviation from the recipe, stated plainly: the recipe says "on ``pema/scheduler``". The jobs table of
package S
(``agent.jobs``) is bound to an account and a thread and runs agent turns or template messages; it has no kind
that calls back into the application. A generic callback job needs a new ``JobKind`` in package S, which O may
not edit, so the durable check lives in its own table with the same guarantees (durable, deduplicated, leased,
retried). It is an open item for the owner whether it should move onto ``pema.scheduler`` later.

Ack and SLA: an acknowledgement of a notice (the operator saw it) does NOT stop M's SLA; only M's
``accept`` or
``decline`` does. A person who reads the notice and walks away must not hold a patient's handoff.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from pema.care.routing_types import SlaCheck
from pema.notify.types import SlaStore
from pema.shared.logger import create_logger

log = create_logger("notify.sla")

DEFAULT_BATCH = 20


def _utc_now() -> datetime:
    return datetime.now(UTC)


class SlaExpiryHandler(Protocol):
    async def on_sla_expired(self, request_id: UUID, idx: int, now: datetime | None = None) -> object: ...


class DurableSlaScheduler:
    """``SlaScheduler`` of package M."""

    def __init__(self, store: SlaStore) -> None:
        self._store = store

    async def schedule_check(self, check: SlaCheck) -> None:
        await self._store.schedule(
            request_id=check.request_id, idx=check.idx, due_at=check.due_at, dedupe_key=check.dedupe_key
        )


class SlaCheckRunner:
    def __init__(
        self,
        store: SlaStore,
        handler: SlaExpiryHandler,
        *,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._store = store
        self._handler = handler
        self._clock = clock

    async def run_once(self, limit: int = DEFAULT_BATCH) -> int:
        """Run every due check once. Returns how many handlers ran to the end."""
        now = self._clock()
        done = 0
        for check in await self._store.claim_due(now, limit):
            ok = False
            try:
                await self._handler.on_sla_expired(check.request_id, check.idx, now)
                ok = True
            except Exception as err:
                log.error(
                    "sla check handler failed", err=err, request_id=str(check.request_id), idx=check.idx
                )
            gave_up = await self._store.finish(check, ok=ok, now=now)
            if ok:
                done += 1
            elif gave_up:
                log.error("sla check given up", request_id=str(check.request_id), idx=check.idx)
        return done
