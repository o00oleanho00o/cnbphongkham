# ported from: src/scheduler/next-run.ts
"""Next run instant, grace window and the decision to take when a job is due.

PURE module like ``schedule_parser``: no DB, no env, no logger. Instants are aware ``datetime`` objects in
and UTC ISO strings (``...Z``, millisecond precision, the shape of JS ``toISOString()``) out, because every
time column of the original stores that string and the ported tests compare against it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from math import floor
from typing import Literal

from pema.scheduler.schedule_parser import cron_iter_for
from pema.shared.zone_time import to_iso_z
from pema_contracts.scheduler import EverySchedule, OnceSchedule, ParsedSchedule

GRACE_MIN_SECONDS = 120
GRACE_MAX_SECONDS = 7200


def compute_next_run(schedule: ParsedSchedule, from_: datetime, now: datetime | None = None) -> str | None:
    """Next run instant.

    ``from_`` is the ANCHOR: at job creation it is "now"; when a job has just become due (the tick writes the
    NEW next_run_at before dispatch) it is the OLD next_run_at, i.e. the instant the job SHOULD have run, not
    the moment the tick actually picked it up.

    ``now`` defaults to ``from_`` (nothing drifted), used at creation. The tick passes the REAL ``now``,
    different from ``from_``, to compensate schedule drift (goclaw ``executeJobByID``): adding only
    ``now + interval`` would let each run that starts a few seconds late accumulate over weeks (7:00 becomes
    7:20). Anchoring on the original ``from_`` and jumping the exact number of elapsed periods
    (``elapsed / interval``) keeps the new instant on the original grid, even after a long catch-up (bot off
    for hours), and never produces a burst of consecutive runs.
    """
    current = now or from_
    if isinstance(schedule, OnceSchedule):
        return schedule.run_at_utc
    if isinstance(schedule, EverySchedule):
        return _compute_every_next(schedule.minutes, from_, current)
    return _compute_cron_next(schedule.expr, schedule.time_zone, current)


def _compute_every_next(minutes: int, from_: datetime, now: datetime) -> str:
    interval = timedelta(minutes=minutes)
    # Clamp at 0: ``now`` earlier than ``from_`` should not happen under the contract, but a negative value
    # would make ``steps`` negative and jump BACKWARDS in time.
    elapsed = max(timedelta(0), now - from_)
    steps = floor(elapsed / interval) + 1
    return to_iso_z(from_ + steps * interval)


def _compute_cron_next(expr: str, time_zone: str, now: datetime) -> str | None:
    # Cron does NOT need the anchor formula of ``every``: each next time is an ABSOLUTE instant of the
    # schedule (7:00 is always 7:00), so asking the library for the next instant AFTER ``now`` is right by
    # itself and accumulates no drift.
    try:
        return to_iso_z(cron_iter_for(expr, time_zone, now).get_next(datetime))
    except Exception:  # an invalid expression gives None (the parser already blocked it earlier)
        return None


def _cron_period_seconds(expr: str, time_zone: str, now: datetime) -> float:
    """Period of the cron expression, estimated from the 2 next instants AFTER ``now``."""
    try:
        interval = cron_iter_for(expr, time_zone, now)
        first: datetime = interval.get_next(datetime)
        second: datetime = interval.get_next(datetime)
    except Exception:
        return float(GRACE_MIN_SECONDS)
    return (second - first).total_seconds()


def grace_seconds_for(
    schedule: ParsedSchedule, once_grace_minutes: float, now: datetime | None = None
) -> float:
    """Grace window (seconds): a delay inside it still counts as "on time".

    ``once`` uses ``once_grace_minutes`` directly (parameter ``SCHEDULER_ONCE_GRACE_MINUTES``).
    ``every``/``cron`` use HALF A PERIOD clamped to ``[120, 7200]`` seconds (the ``_compute_grace_seconds``
    formula of Hermes): a dense job (every 5 minutes) should not have a grace longer than its own period, a
    sparse job (every 3 days) should not have 1.5 days of grace either; a 2 hour ceiling is enough for "the
    bot just restarted" without turning into "catch up after half a day"."""
    if isinstance(schedule, OnceSchedule):
        return once_grace_minutes * 60

    if isinstance(schedule, EverySchedule):
        period_seconds = float(schedule.minutes * 60)
    else:
        period_seconds = _cron_period_seconds(schedule.expr, schedule.time_zone, now or datetime.now(UTC))

    return min(float(GRACE_MAX_SECONDS), max(float(GRACE_MIN_SECONDS), period_seconds / 2))


@dataclass(frozen=True)
class DueJob:
    schedule: ParsedSchedule
    next_run_at: datetime
    """``next_run_at`` on the row: the instant the job SHOULD have run."""
    once_grace_minutes: float


type DueAction = Literal["run", "run-late", "skip-forward"]


def decide_due_action(job: DueJob, now: datetime) -> DueAction:
    """The job is DUE (the caller filtered with ``next_run_at <= now``): decide how to run it. Matches the
    4-line "bot off then on again" table:

    ====================================  =============  ==========================================
    situation                             returns
    ====================================  =============  ==========================================
    once, late inside the grace           ``run``
    once, late beyond the grace           ``run-late``   (still sent, with a "late reminder" label)
    every/cron, late inside the grace     ``run``        (catch up once)
    every/cron, late beyond the grace     ``skip-forward``  (skip the slot, no backlog)
    ====================================  =============  ==========================================

    ``once`` has no ``skip-forward``: silently swallowing an APPOINTMENT reminder is the worst outcome for a
    personal bot: however late, it has to be reported, the only difference is whether it carries the label
    (a deliberate decision unlike Hermes, where an overdue one-shot is dropped).
    """
    grace_seconds = grace_seconds_for(job.schedule, job.once_grace_minutes, now)
    late_seconds = (now - job.next_run_at).total_seconds()
    on_time = late_seconds <= grace_seconds

    if isinstance(job.schedule, OnceSchedule):
        return "run" if on_time else "run-late"
    return "run" if on_time else "skip-forward"
