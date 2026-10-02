"""The daily tick at 06:00 ``Asia/Ho_Chi_Minh`` (PLAN-AI01-M sections 2 and 3). New module (not a port).

The tick walks every active care agent in batches (keyset pagination on the id, ``TICK_BATCH_SIZE`` per batch)
and asks the rules (``TickRuleSource``: missed milestone, stale pending work ...) what needs doing. The rules
need no LLM and are one query per batch, never one per patient. The LLM is only called for a patient whose
findings say a text must be drafted: ONE ``daily_tick`` event per such patient (all their findings in the
payload) goes on the priority queue at the lowest level, and the worker runs it like any other turn. So the
number of LLM calls of a tick is at most the number of patients that genuinely need a draft.

Running the tick twice the same day queues the drafts twice (``last_tick_at`` is also set by every ordinary
turn, so it cannot tell whether the tick ran): the scheduler that fires it (S, cron ``0 6 * * *``) is the one
that must fire it once.

``seconds_until_next_tick`` is for the loop that sleeps until 06:00.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from pema.care.events import CareEvent, EventKind, Initiator
from pema.care.ports import CareStore, TickFinding, TickRuleSource
from pema.care.priority import CarePriorityQueue

logger = logging.getLogger(__name__)

TICK_TIME = time(6, 0)
TICK_TIME_ZONE = "Asia/Ho_Chi_Minh"
TICK_BATCH_SIZE = 100


@dataclass(frozen=True)
class TickReport:
    agents_checked: int
    findings: int
    drafts_enqueued: int
    batches: int


def next_tick_at(now: datetime) -> datetime:
    """The next 06:00 local time strictly after ``now`` (UTC)."""
    zone = ZoneInfo(TICK_TIME_ZONE)
    local = now.astimezone(zone)
    candidate = datetime.combine(local.date(), TICK_TIME, tzinfo=zone)
    if candidate <= local:
        candidate = datetime.combine(local.date() + timedelta(days=1), TICK_TIME, tzinfo=zone)
    return candidate.astimezone(UTC)


def seconds_until_next_tick(now: datetime) -> float:
    return (next_tick_at(now) - now).total_seconds()


async def daily_tick(
    clinic_id: UUID,
    now: datetime,
    *,
    store: CareStore,
    rules: TickRuleSource,
    queue: CarePriorityQueue,
    batch_size: int = TICK_BATCH_SIZE,
) -> TickReport:
    """Run the tick at the instant ``now`` (read once by the caller)."""
    checked = findings_total = drafts = batches = 0
    after: UUID | None = None
    while True:
        batch = list(await store.list_active_care_agents(after=after, limit=batch_size))
        if not batch:
            break
        after = batch[-1].id
        batches += 1
        agents = [agent for agent in batch if agent.clinic_id == clinic_id]
        checked += len(agents)
        found = await rules.findings(agents, now)
        findings_total += len(found)

        by_agent: dict[UUID, list[TickFinding]] = {}
        for finding in found:
            if finding.needs_draft:
                by_agent.setdefault(finding.care_agent_id, []).append(finding)
        for care_agent_id, items in by_agent.items():
            queue.push(
                care_agent_id,
                CareEvent(
                    kind=EventKind.DAILY_TICK,
                    initiator=Initiator.SYSTEM,
                    patient_ref=items[0].patient_ref,
                    payload={"findings": [{"kind": item.kind, **item.payload} for item in items]},
                    occurred_at=now,
                ),
            )
            drafts += 1

        await store.touch_last_tick([agent.id for agent in agents], now)
        if len(batch) < batch_size:
            break
    logger.info(
        "care tick",
        extra={"agents": checked, "findings": findings_total, "drafts": drafts, "batches": batches},
    )
    return TickReport(
        agents_checked=checked, findings=findings_total, drafts_enqueued=drafts, batches=batches
    )
