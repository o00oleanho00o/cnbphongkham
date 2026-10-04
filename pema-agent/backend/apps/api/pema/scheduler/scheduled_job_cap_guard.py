# ported from: src/scheduler/scheduled-job-cap-guard.ts
"""Handling of a run blocked by the DAILY CAP - unlike the other "not ready" reasons (account/thread, see
``conclude_blocked_not_run`` in ``scheduled_job_conclude``) in that a 'once' job must NOT move ``next_run_at``
back to a past instant (the next tick would hit the cap again, exactly the LLM-burning loop every 30 s that
this fixes): it has to be pushed to the CONFIGURABLE hour (``SCHEDULER_DEFERRED_RUN_HOUR``) of TOMORROW,
matching the sentence the bot just sent "the remaining schedules will continue tomorrow". Split from
``scheduled_job_conclude`` to keep that file small - this is purely the "daily cap" branch of concluding a
run.

2 call sites:

* ``conclude_cap_blocked``: already has ``run_id``/``target`` (from ``blocked_by_guard`` at dispatch - taking
  the slot ATOMICALLY failed there).
* ``conclude_cap_blocked_at_tick``: called BEFORE dispatch (``scheduler_loop``, the early PURE-READ filter) -
  nothing is ready yet, it opens the target itself (the loop already opened the run in the claim transaction
  and passes its id).

Clinic addition: the cap notice is a text that goes OUT to a person. Under a profile whose outbound mode is
``review`` (``patient_channel``) nothing is ever sent by the scheduler on its own, so the notice is never
sent there (a job that only drafts does not consume slots either, see ``scheduled_job_send``).
"""

from __future__ import annotations

from datetime import datetime

from pema.config.runtime_tuning_settings import get_tuning_int
from pema.scheduler.deps import SchedulerDeps
from pema.scheduler.job_run_log_store import FinishRunParams
from pema.scheduler.ports import ReplyTarget
from pema.scheduler.proactive_send_guard import EffectiveCap
from pema.scheduler.scheduled_job_reply_target import make_job_target
from pema.shared.logger import create_logger
from pema.shared.zone_time import deferred_run_at_utc
from pema_contracts.conversation import StoredMessage
from pema_contracts.policy import OutboundMode, PolicyContext
from pema_contracts.scheduler import JobRunStatus, ScheduledJob, ScheduleKind

log = create_logger("run-scheduled-job")


async def conclude_cap_blocked(
    deps: SchedulerDeps,
    job: ScheduledJob,
    run_id: int,
    reason: str,
    time_zone: str,
    now: datetime,
    *,
    cap: EffectiveCap,
    ctx: PolicyContext,
    notify_cap_hit_once: bool,
    target: ReplyTarget | None = None,
    turn_id: int | None = None,
) -> None:
    """Conclude a run blocked by the DAILY CAP, with ``run_id`` already opened. ``every``/``cron`` do not
    touch ``next_run_at`` - ``scheduler_loop`` already computed the right next slot of that very schedule
    before getting here. Resets ``delivery_attempts``: this run ended NOT because of a failed send (the real
    payload was never even tried) - a chain of failed sends of other runs must not accumulate through a run
    blocked by this cap."""
    async with deps.db.session() as s:
        if job.schedule_kind is ScheduleKind.ONCE:
            await deps.jobs.set_next_run(
                job.clinic_id,
                job.id,
                deferred_run_at_utc(time_zone, get_tuning_int("SCHEDULER_DEFERRED_RUN_HOUR"), now),
                session=s,
            )
        await deps.runs.finish_run(
            job.clinic_id,
            run_id,
            FinishRunParams(status=JobRunStatus.SKIPPED, detail=reason, turn_id=turn_id),
            session=s,
        )
        await deps.attempts.reset_delivery_attempts(job.clinic_id, job.id, session=s)

    if notify_cap_hit_once and target is not None:
        await _notify_cap_hit(deps, job, target, cap, ctx, time_zone, now)


async def conclude_cap_blocked_at_tick(
    deps: SchedulerDeps,
    job: ScheduledJob,
    run_id: int,
    reason: str,
    notify_cap_hit_once: bool,
    time_zone: str,
    now: datetime,
    *,
    cap: EffectiveCap,
    ctx: PolicyContext,
) -> None:
    """Version used at the TICK, BEFORE dispatch (``scheduler_loop``) - there is no ``target`` yet (the
    channel is not resolved) as at dispatch time, it takes care of that itself. NEVER raises: it is called NOT
    AWAITED from the tick, the hard rule of the whole tick loop (see ``scheduler_loop``)."""
    try:
        # Goes through the SAME factory as the main send path (``scheduled_job_reply_target``). The earlier
        # version built the zca-js path by hand here, so for a bot account the target was undefined ->
        # ``notify_cap_hit_once`` became false -> NOBODY WAS TOLD that the daily cap was reached. A silent
        # failure, exactly the kind that "fixing only the main send path" misses.
        job_target = make_job_target(deps.channels, job) if notify_cap_hit_once else None
        target = job_target.target if job_target is not None else None
        await conclude_cap_blocked(
            deps,
            job,
            run_id,
            reason,
            time_zone,
            now,
            cap=cap,
            ctx=ctx,
            notify_cap_hit_once=target is not None,
            target=target,
        )
    except Exception as err:
        log.error("Lỗi kết luận job bị chặn ở trần ngày ngay tại tick", job_id=job.id, err=err)


async def _notify_cap_hit(
    deps: SchedulerDeps,
    job: ScheduledJob,
    target: ReplyTarget,
    cap: EffectiveCap,
    ctx: PolicyContext,
    time_zone: str,
    now: datetime,
) -> None:
    """Win the RIGHT to send the notice ATOMICALLY first (``reserve_cap_notice``) and only then really send -
    this is the point that blocks the race of N jobs of the same scope blocked in the SAME tick (before the
    fix: the decision "is it the first time the cap is hit" was read BEFORE the send, and the send path had to
    wait ``SCHEDULER_SEND_GAP_MS``, so all N jobs thought they were the first). A failed send ->
    ``revert_cap_notice`` hands the right back.

    ``now`` comes from ``conclude_cap_blocked`` (no ``datetime.now()`` here): reserve/revert must have the
    same ``day_key`` as the very run being handled - close to midnight, taking the real time here could slip
    to TOMORROW relative to the ``now`` the caller holds, writing "announced" on the wrong day so that the
    next day's real cap hit would have no notice at all."""
    if ctx.profile.outbound_mode is OutboundMode.REVIEW:
        return  # nothing goes out on its own under a review profile (see the module docstring)
    if not await deps.guard.reserve_cap_notice(job.clinic_id, cap.scope_key, time_zone, now):
        return  # another job/tick already won it or already sent it
    notified = await _send_cap_notice(deps, job, target, cap, time_zone, now)
    if not notified:
        await deps.guard.revert_cap_notice(job.clinic_id, cap.scope_key, time_zone, now)


async def _send_cap_notice(
    deps: SchedulerDeps,
    job: ScheduledJob,
    target: ReplyTarget,
    cap: EffectiveCap,
    time_zone: str,
    now: datetime,
) -> bool:
    """Send EXACTLY 1 sentence when the daily cap is first hit. Returns ``True`` when it really went out - the
    caller keeps the right "already announced" only then."""
    try:
        text = (
            f"Hôm nay cuộc trò chuyện này đã nhận đủ {cap.max_per_day} tin nhắc/báo cáo chủ động, "
            "mình tạm dừng để tránh làm phiền - các lịch còn lại sẽ tiếp tục vào ngày mai."
        )

        async def send() -> bool:
            reply = await deps.outbound.send_reply_in_parts(target, text)
            if reply.delivered_text:
                try:
                    await deps.history.append_message(
                        job.clinic_id,
                        job.account_id,
                        job.thread_id,
                        StoredMessage(role="assistant", content=reply.delivered_text),
                    )
                except Exception as err:
                    # The notice ALREADY went out - a failed history write must NOT turn "sent" into "not
                    # sent" (the same bug as Item 2): raising here would make the outer ``except`` return
                    # False -> ``revert_cap_notice`` -> a later job/tick would send the same notice AGAIN
                    # although this one did arrive.
                    log.error(
                        "Ghi history thông báo chạm trần sau khi gửi thành công bị lỗi - vẫn coi là ĐÃ GỬI",
                        err=err,
                        job_id=job.id,
                    )
                await deps.guard.record_proactive_send(
                    job.clinic_id, cap.scope_key, time_zone, reply.sent_parts, now
                )
            # Only whether it went out (``delivered_text``) - NOT ``reply.error`` (Item 3, round 4): the
            # notice may have really gone out and only then failed at the history write; returning ``False``
            # then would make the caller ``revert_cap_notice`` and the next tick would SEND THE NOTICE AGAIN.
            return bool(reply.delivered_text)

        return await deps.queue.deliver_proactively(job.clinic_id, job.account_id, job.thread_id, send)
    except Exception as err:
        log.error("Gửi thông báo chạm trần thất bại - bỏ qua, không chặn việc ghi run skipped", err=err)
        return False
