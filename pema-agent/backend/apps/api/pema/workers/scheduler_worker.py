"""Process entry point of the scheduler (new module: the ``startScheduler`` / ``stopScheduler`` calls of
``src/index.ts`` and its shutdown hook, package S).

It runs with the ``agent_worker`` database role: the loop reads and writes ``agent.*`` and reaches the clinic
only through the ``clinic_agent`` views/functions (``list_active_clinic_ids`` to find the clinics,
``channel_policy``, ``message_template_approved``, ``patient_ref``, ``create_review_item``).

This module only ASSEMBLES the loop; the objects it needs from other packages (channel registry with the
running accounts, agent engine, outbound pipeline, stores) are built by the composition root
(``pema.workers.main``, package G) and passed in through ``SchedulerDeps``. Several worker processes may run
this loop at once: the atomic claim and the cap counters keep every job single-run; the optional Redis lease
only avoids redundant scans."""

from __future__ import annotations

import asyncio
from uuid import UUID

from pema.config.runtime_tuning_settings import get_tuning_int
from pema.scheduler.deps import SchedulerDeps
from pema.scheduler.redis_locks import LockBackend, LockSendGate, TickLease
from pema.scheduler.scheduler_loop import ClinicIds, SchedulerLoop
from pema.shared.logger import create_logger

log = create_logger("scheduler-worker")


def build_scheduler_loop(
    deps: SchedulerDeps,
    *,
    lock_backend: LockBackend | None = None,
    clinic_ids: ClinicIds | None = None,
) -> SchedulerLoop:
    """The loop of one worker. ``lock_backend`` (Redis in production) enables the per-clinic tick lease; the
    send gate that spaces the SAME account across processes must be given to ``SchedulerDeps`` (see
    ``build_send_gate``) because the queue that uses it lives inside the deps."""
    lease = TickLease(lock_backend, lambda: get_tuning_int("SCHEDULER_TICK_MS")) if lock_backend else None
    return SchedulerLoop(deps, clinic_ids=clinic_ids, tick_lease=lease)


def build_send_gate(lock_backend: LockBackend) -> LockSendGate:
    """``SendGate`` for ``SchedulerDeps(send_gate=...)``: one proactive send per ``SCHEDULER_SEND_GAP_MS`` per
    (clinic, account) across worker processes."""
    return LockSendGate(lock_backend)


async def run_scheduler_worker(
    deps: SchedulerDeps,
    *,
    lock_backend: LockBackend | None = None,
    stop: asyncio.Event | None = None,
    clinic_ids: ClinicIds | None = None,
) -> None:
    """Start the loop, wait for ``stop`` (a signal handler of the entry point sets it), then shut down: stop
    the timer and wait for the runs in flight so their ledger rows are closed. ``stop`` omitted = run until
    cancelled."""
    loop = build_scheduler_loop(deps, lock_backend=lock_backend, clinic_ids=clinic_ids)
    await loop.start()
    log.info("Scheduler worker đã chạy", worker_id=deps.worker_id)
    try:
        if stop is None:
            await asyncio.Event().wait()
        else:
            await stop.wait()
    finally:
        await loop.stop()
        await loop.wait_idle()
        log.info("Scheduler worker đã dừng", worker_id=deps.worker_id)


async def recover_clinics(deps: SchedulerDeps, clinic_ids: list[UUID]) -> None:
    """One-shot recovery for a CLI / ops use (``interrupt_stale_runs`` + ``revive_claimed_once``) without
    starting the loop."""
    loop = SchedulerLoop(deps)
    for clinic_id in clinic_ids:
        await loop.recover_clinic(clinic_id)
