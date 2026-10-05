# ported from: src/scheduler/scheduler-loop.ts
"""The tick loop: scan due jobs -> PRE-FLIGHT check (account/thread + daily cap, cheap, does not touch the LLM
when blocked) -> decide run/run-late/skip-forward -> clear-before-dispatch -> dispatch NOT AWAITED.

"No await in the tick" is the hardest rule here (goclaw learned it in blood: ``wg.Wait()`` inside the loop
stalled the whole scheduler) - an agent job can run for a few minutes, blocking the next tick blocks EVERY
other thread, not just that job. Dispatch is ``asyncio.create_task``; the tasks are kept in a set (an
unreferenced task can be garbage collected mid-run) and ``wait_idle`` lets a test await them.

Do NOT wrap the whole ``run_scheduled_job`` in the thread lock here (the thread lock is held ONLY while really
sending, inside ``deliver_proactively`` - wrapping at this layer would nest 2 locks for the SAME thread and
deadlock).

Forced deviations (one process -> several workers over the ONE clinic of the installation):

* ``startScheduler`` / ``runSchedulerTick`` become ``SchedulerLoop.start`` / ``run_tick(clinic_id, now)``; the
  clinic is the installation clinic (single tenant, ``get_installation_clinic_id``), there is no loop over
  clinics (the worker, ``pema.workers.scheduler_worker``, owns the process);
* "clear-before-dispatch" is an ATOMIC claim (compare-and-swap on ``next_run_at``) in the SAME transaction
  that opens the run: of N workers that read the same due row exactly one gets ``True`` and runs it, and a
  crash cannot leave a claimed job without a ``running`` row. This is the invariant "a job never runs twice"
  that a single synchronous process gave for free;
* boot recovery needs a heartbeat (see ``interrupt_stale_runs``), so it also runs periodically, not only at
  boot, because a worker that died while others stayed up must still be recovered;
* an optional ``TickLease`` (Redis) lets one worker scan a clinic per tick; correctness never depends on it.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Coroutine
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text

from pema.config.runtime_tuning_settings import bot_time_zone, get_tuning_bool, get_tuning_int
from pema.core.db import get_installation_clinic_id
from pema.scheduler.deps import SchedulerDeps
from pema.scheduler.job_run_log_store import FinishRunParams
from pema.scheduler.next_run import DueJob, compute_next_run, decide_due_action
from pema.scheduler.redis_locks import TickLease
from pema.scheduler.run_context import resolve_policy_context
from pema.scheduler.run_scheduled_job import RunScheduledJobOptions, run_scheduled_job
from pema.scheduler.scheduled_job_cap_guard import conclude_cap_blocked_at_tick
from pema.scheduler.scheduled_job_record import schedule_of
from pema.scheduler.session_scope import parse_utc
from pema.shared.logger import create_logger
from pema_contracts.policy import OutboundMode
from pema_contracts.scheduler import JobKind, JobRunStatus, ScheduledJob, ScheduleKind

log = create_logger("scheduler-loop")


class SchedulerLoop:
    def __init__(
        self,
        deps: SchedulerDeps,
        *,
        tick_lease: TickLease | None = None,
    ) -> None:
        self._deps = deps
        self._tick_lease = tick_lease
        self._task: asyncio.Task[None] | None = None
        self._tasks: set[asyncio.Task[None]] = set()
        # Last PRE-FLIGHT block reason per job - log again only when the reason CHANGES, to avoid spamming
        # every 30 s when an account is offline for days.
        self._last_preflight_reason: dict[tuple[UUID, str], str] = {}
        self._last_recovery: dict[UUID, float] = {}

    # ------------------------------------------------------------------------------------ lifecycle

    async def start(self) -> None:
        """Call after the accounts are started at boot. Safe to call again (no-op when already running)."""
        if not get_tuning_bool("SCHEDULER_ENABLED"):
            log.info("SCHEDULER_ENABLED=false - không đăng ký vòng tick, job vẫn nằm nguyên trong DB")
            return
        if self._task is not None:
            return  # already running - calling twice must not double the tick loop

        await self.recover_clinic(await get_installation_clinic_id(self._deps.db))

        self._task = asyncio.create_task(self._run_forever())
        log.info("Scheduler đã khởi động", tick_ms=get_tuning_int("SCHEDULER_TICK_MS"))

    async def stop(self) -> None:
        """Call in the shutdown. Safe to call even when never started. Does not cancel runs in flight (their
        ``running`` rows are recovered by the heartbeat if the process dies)."""
        task, self._task = self._task, None
        if task is None:
            return
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    async def wait_idle(self) -> None:
        """Wait for every dispatched run to finish (tests and graceful shutdown)."""
        while self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

    async def _run_forever(self) -> None:
        # Run NOW, do not wait the whole first SCHEDULER_TICK_MS - an overdue job (the bot just restarted
        # after a pause) is handled at once, through exactly the grace/skip-forward mechanism used on every
        # tick - no separate branch for "boot time".
        while True:
            try:
                await self.run_tick_all(datetime.now(UTC))
            except Exception as err:  # one failed iteration must not stop the loop
                log.error("Tick lỗi - vòng lặp vẫn tiếp tục ở lần kế", err=err)
            await asyncio.sleep(get_tuning_int("SCHEDULER_TICK_MS") / 1000)

    # -------------------------------------------------------------------------------------- recovery

    async def recover_clinic(self, clinic_id: UUID) -> None:
        """Boot / periodic recovery of one clinic: ``running`` rows of dead workers become 'interrupted', and
        the 'once' reminders they had claimed are given back (see ``revive_claimed_once``)."""
        deps = self._deps
        interrupted = await deps.runs.interrupt_stale_runs(clinic_id, deps.stale_run_seconds)
        if interrupted > 0:
            log.warning(
                "Đánh dấu các lượt job dở dang từ lần chạy trước là 'interrupted'", interrupted=interrupted
            )
        # Runs BEFORE the first tick of the clinic: pick up the 'once' reminders claimed halfway at a restart.
        revived = await deps.jobs.revive_claimed_once(clinic_id)
        if revived > 0:
            log.warning(
                "Phục hồi next_run_at cho lời nhắc 'once' bị giành (clear-before-dispatch) nhưng worker bị "
                "giết trước khi kịp chạy xong",
                revived=revived,
            )
        self._last_recovery[clinic_id] = time.monotonic()

    async def _recover_if_due(self, clinic_id: UUID) -> None:
        last = self._last_recovery.get(clinic_id)
        if last is not None and time.monotonic() - last < max(1.0, self._deps.stale_run_seconds / 2):
            return
        await self.recover_clinic(clinic_id)

    # ------------------------------------------------------------------------------------------ tick

    async def run_tick_all(self, now: datetime) -> None:
        """One tick over the clinic of the installation."""
        if not get_tuning_bool("SCHEDULER_ENABLED"):
            return
        clinic_id = await get_installation_clinic_id(self._deps.db)
        if self._tick_lease is not None and not await self._tick_lease.try_hold(clinic_id):
            return
        await self._recover_if_due(clinic_id)
        await self.run_tick(clinic_id, now)

    async def run_tick(self, clinic_id: UUID, now: datetime) -> None:
        """1 scan of the due jobs of one clinic. Public (not only reachable through the timer) so a test calls
        it directly without waiting for a real timer."""
        # Read AGAIN every tick, not only at ``start``: SCHEDULER_ENABLED is a hot-tunable parameter, the
        # philosophy of ``get_tuning`` "read again each time" of the whole project. Without this line turning
        # the flag off on the dashboard while the bot runs would do nothing - the timer registered at
        # ``start`` would keep going, and a safety switch that cannot really switch off is meaningless.
        if not get_tuning_bool("SCHEDULER_ENABLED"):
            return

        # One broken job must not kill the loop (goclaw safeCheckJobs) - wrap the WHOLE tick, not only each
        # job: an unexpected error right in ``list_due_jobs`` must not stop the next tick either.
        try:
            due = await self._deps.jobs.list_due_jobs(clinic_id, now)
            self._prune_stale_reasons(clinic_id, due)
            for job in due:
                await self._process_due_job(job, now)
        except Exception as err:
            log.error("Tick lỗi - vòng lặp vẫn tiếp tục ở lần kế", err=err)

    def _prune_stale_reasons(self, clinic_id: UUID, due: list[ScheduledJob]) -> None:
        """A job that is NO LONGER due (deleted, or its ``next_run_at`` changed) drops its old block trace -
        avoids a memory leak, the same reason ``threadChains`` of the batcher must clean itself: a job deleted
        EXACTLY while blocked would leave an entry forever if cleaned only on the "passed pre-flight"
        branch."""
        if not self._last_preflight_reason:
            return
        due_ids = {(clinic_id, j.id) for j in due}
        for key in [k for k in self._last_preflight_reason if k[0] == clinic_id and k not in due_ids]:
            del self._last_preflight_reason[key]

    def _spawn(self, coro: Coroutine[Any, Any, None]) -> None:
        """Dispatch NOT AWAITED (the hard rule of the whole tick): the task keeps running after the tick."""
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _process_due_job(self, job: ScheduledJob, now: datetime) -> None:
        deps = self._deps
        key = (job.clinic_id, job.id)
        try:
            # Check the CHEAP part (no LLM cost, no ``usage`` row) BEFORE clear-before-dispatch. Blocked here
            # the tick does NOT touch next_run_at/run_count/enabled of the job - the next tick retries by
            # itself. Mandatory invariant: "a reminder that never ran is never counted as run" - an account
            # that dropped its session (a perfectly normal case with zca-js) exactly when the job became due
            # must not kill the job.
            preflight = await deps.guard.check_account_and_thread_ready(
                job.clinic_id, job.account_id, job.thread_id, now
            )
            if not preflight.ok:
                if self._last_preflight_reason.get(key) != preflight.reason:
                    self._last_preflight_reason[key] = preflight.reason
                    log.warning(
                        "Job chưa dispatch được - tick sau thử lại", job_id=job.id, reason=preflight.reason
                    )
                    async with deps.db.session() as s:
                        await deps.jobs.mark_blocked(job.clinic_id, job.id, preflight.reason, session=s)
                        # NOT because of a failed send - this is the MOST COMMON block in production
                        # (account/thread blocked right at the tick). Without this line: 3 failed sends WEEKS
                        # APART still add up to 3, a 'once' job is switched off for good - a reminder lost
                        # although it never failed 3 times CONSECUTIVELY.
                        await deps.attempts.reset_delivery_attempts(job.clinic_id, job.id, session=s)
                return
            self._last_preflight_reason.pop(key, None)  # passed - clear the trace of the previous block

            schedule = schedule_of(job, bot_time_zone())
            # 'once' uses ``run_at`` (the ORIGINAL instant, never overwritten) to compute the delay + the
            # "late reminder" label - ``next_run_at`` may have been pushed by the daily cap or restored by a
            # failed send, using it would LOSE the label for a job just postponed overnight. every/cron have
            # no run_at (NULL) so they still use next_run_at.
            scheduled_for = job.run_at if schedule.kind is ScheduleKind.ONCE else job.next_run_at
            scheduled_dt = parse_utc(scheduled_for)
            expected_dt = parse_utc(job.next_run_at)
            if scheduled_dt is None or expected_dt is None or scheduled_for is None:
                return  # a due job always has both instants (list_due_jobs filters next_run_at IS NOT NULL)
            action = decide_due_action(
                DueJob(
                    schedule=schedule,
                    next_run_at=scheduled_dt,
                    once_grace_minutes=get_tuning_int("SCHEDULER_ONCE_GRACE_MINUTES"),
                ),
                now,
            )

            # Clear-before-dispatch: write the NEW next_run_at before dispatching so the next tick does not
            # pick up this very job while it is still running. 'once' has no real "next slot"
            # (``compute_next_run`` returns the OLD ``run_at_utc`` whatever ``now`` is) so it has to be
            # cleared straight to NULL - leaving the old instant would be picked again by the very next tick.
            next_run_at = (
                None if schedule.kind is ScheduleKind.ONCE else compute_next_run(schedule, scheduled_dt, now)
            )

            # The claim is ATOMIC (compare-and-swap on next_run_at) and opens the run in the SAME transaction.
            async with deps.db.session() as s:
                claimed = await deps.jobs.claim_due_job(
                    job.clinic_id, job.id, expected_dt, next_run_at, session=s
                )
                if not claimed:
                    return  # another worker (or a trial run) took this occurrence first
                run_id = await deps.runs.open_run(job.clinic_id, job.id, worker_id=deps.worker_id, session=s)
                if action == "skip-forward":
                    # Skip the slot ENTIRELY: every/cron later than the grace, "catching up" would pile up a
                    # backlog. Write 'skipped' AT ONCE so the dashboard sees why the next slot jumped far.
                    await deps.runs.finish_run(
                        job.clinic_id,
                        run_id,
                        FinishRunParams(
                            status=JobRunStatus.SKIPPED,
                            detail="Bỏ lượt vì đã trễ quá cửa sổ grace - dời sang lần kế tiếp.",
                        ),
                        session=s,
                    )
                    # NOT because of a failed send - only every/cron reach this branch
                    await deps.attempts.reset_delivery_attempts(job.clinic_id, job.id, session=s)
            if action == "skip-forward":
                log.info("Job trễ quá grace - bỏ lượt, dời lịch", job_id=job.id, next_run_at=next_run_at)
                return

            # Filter the daily cap EARLY, BEFORE dispatch (Item 1) - PURE READ, reserves nothing (the REAL
            # reservation happens right at the send, see ``blocked_by_guard``). Without this step a job at the
            # cap would burn a whole LLM turn every 30 seconds until the end of the day.
            time_zone = job.timezone or bot_time_zone()
            account = await deps.accounts.get_account(job.clinic_id, job.account_id)
            if account is not None:
                policy = await resolve_policy_context(deps, job, account, isolated=job.kind is JobKind.AGENT)
                cap = await deps.guard.effective_cap(policy, deps.hooks)
                # Under a ``review`` profile the run only DRAFTS: nothing is sent, so the cap (a limit on sent
                # messages) does not apply here; it is applied when a person approves and the text goes out.
                if policy.profile.outbound_mode is not OutboundMode.REVIEW:
                    verdict = await deps.guard.check_proactive_daily_cap(
                        job.clinic_id, cap.scope_key, time_zone, now, cap.max_per_day
                    )
                    if not verdict.ok:
                        # Not awaited (the hard rule of the whole tick) - the function promises never to raise
                        # (internal try/except, see ``scheduled_job_cap_guard``).
                        self._spawn(
                            conclude_cap_blocked_at_tick(
                                deps,
                                job,
                                run_id,
                                verdict.reason,
                                verdict.notify_cap_hit_once,
                                time_zone,
                                now,
                                cap=cap,
                                ctx=policy,
                            )
                        )
                        return

            # NOT awaited: the hardest rule of the whole tick (see the header). The thread lock is NOT wrapped
            # here either - see the header for why (deadlock).
            self._spawn(
                run_scheduled_job(
                    deps,
                    job,
                    RunScheduledJobOptions(
                        late=action == "run-late", scheduled_for=scheduled_for, now=now, run_id=run_id
                    ),
                )
            )
        except Exception as err:
            # One broken job must not kill the tick - the OTHER jobs of the SAME tick still have to be handled
            # (goclaw safeCheckJobs, the same reason as the try/except above but at the level of EACH JOB
            # instead of the whole tick).
            log.error("Lỗi xử lý 1 job đến hạn - bỏ qua job này, tick vẫn tiếp tục", job_id=job.id, err=err)


async def count_running_rows(deps: SchedulerDeps, clinic_id: UUID) -> int:
    """Diagnostics for tests and the admin API: how many runs are open in the clinic right now."""
    async with deps.db.session() as s:
        value = (
            await s.execute(
                text(
                    "SELECT count(*) FROM agent.job_runs WHERE clinic_id = :clinic_id AND status = 'running'"
                ),
                {"clinic_id": clinic_id},
            )
        ).scalar_one()
    return int(value)
