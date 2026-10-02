"""The clinic's 24/7 on-call Zalo contact (PLAN-AI01-M sections 7 and 11). New module (not a port).

The number lives in ``clinic.on_call_contacts`` (entered on the dashboard), NEVER in code or in the
repository; the worker reads it through the view ``clinic_agent.on_call_contact``. ``OnCallDirectory``
reads it on EVERY call, so a change of the number takes effect on the very next turn:

* ``current_on_call(clinic_id, now)``: the active row whose validity covers ``now`` (``pick_on_call``; when
  several rows are valid the one that became valid last wins, ties go to the larger id, so the choice is
  deterministic). ``None`` when the clinic has not configured one (the caller logs it; the chain still ends
  with an on-call entry, see ``pema.care.routing``).
* ``cache_ttl_seconds``: an optional cache of the raw rows, at most ``MAX_CACHE_TTL_SECONDS`` (60 s; any
  larger value is clamped). The default is 0: no cache, the database is read every time (a handoff is rare
  and the query is one tiny SELECT).
* ``record_use``: every use of the number (a candidate chain that ends with it, the message to the on-call
  contact, the number given to a patient) writes one ``actions_log`` line ``oncall_used:<purpose>`` for the
  care agent concerned (PLAN-M section 11, rule 7). The line carries no number.

The number itself is never logged.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from datetime import datetime
from typing import Protocol
from uuid import UUID

from pema.care.models import ActionDisposition
from pema.care.ports import OnCallSource
from pema.care.routing_types import OnCallInfo, OnCallRow

logger = logging.getLogger(__name__)

MAX_CACHE_TTL_SECONDS = 60.0
ONCALL_USED = "oncall_used"
"""``actions_log.action_type`` prefix: ``oncall_used:<purpose>``."""

PURPOSE_CHAIN = "chain"
PURPOSE_NOTIFY = "notify"
PURPOSE_PATIENT_NOTICE = "patient_notice"


class ActionRecorder(Protocol):
    """The one method of ``CareStore`` / ``RoutingStore`` that ``OnCallDirectory`` needs."""

    async def record_action(
        self,
        care_agent_id: UUID,
        *,
        action_type: str,
        disposition: str,
        depth: str | None,
        at: datetime,
    ) -> None: ...


def pick_on_call(rows: Sequence[OnCallRow], now: datetime) -> OnCallRow | None:
    """The row that is active and valid at ``now``; the latest ``valid_from`` wins, then the larger id."""
    valid = [
        row
        for row in rows
        if row.active and row.valid_from <= now and (row.valid_to is None or now < row.valid_to)
    ]
    if not valid:
        return None
    return max(valid, key=lambda row: (row.valid_from, row.id.int))


class OnCallDirectory:
    def __init__(
        self,
        source: OnCallSource,
        recorder: ActionRecorder | None = None,
        *,
        cache_ttl_seconds: float = 0.0,
        monotonic: Callable[[], float] | None = None,
    ) -> None:
        self._source = source
        self._recorder = recorder
        self._ttl = min(max(cache_ttl_seconds, 0.0), MAX_CACHE_TTL_SECONDS)
        self._monotonic = monotonic
        self._cache: dict[UUID, tuple[float, Sequence[OnCallRow]]] = {}

    async def _rows(self, clinic_id: UUID, now: datetime) -> Sequence[OnCallRow]:
        if self._ttl <= 0 or self._monotonic is None:
            return await self._source.active_contacts(clinic_id)
        tick = self._monotonic()
        cached = self._cache.get(clinic_id)
        if cached is not None and tick - cached[0] < self._ttl:
            return cached[1]
        rows = await self._source.active_contacts(clinic_id)
        self._cache[clinic_id] = (tick, rows)
        return rows

    async def current_on_call(self, clinic_id: UUID, now: datetime) -> OnCallInfo | None:
        row = pick_on_call(await self._rows(clinic_id, now), now)
        if row is None:
            logger.error("no active on-call contact is configured")
            return None
        return OnCallInfo(id=row.id, zalo_number=row.zalo_number, owner=row.owner, is_fixture=row.is_fixture)

    async def record_use(self, care_agent_id: UUID, purpose: str, depth: str | None, at: datetime) -> None:
        if self._recorder is None:
            return
        await self._recorder.record_action(
            care_agent_id,
            action_type=f"{ONCALL_USED}:{purpose}",
            disposition=ActionDisposition.PAUSED.value,
            depth=depth,
            at=at,
        )
