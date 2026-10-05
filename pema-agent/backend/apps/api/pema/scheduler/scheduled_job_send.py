# ported from: src/scheduler/scheduled-job-send.ts
"""REALLY send 1 run of a job: the guard before sending (take 1 daily-cap slot ATOMICALLY), send through
``deliver_proactively``, then close the books. Split from ``scheduled_job_conclude`` (which keeps the COMMON
conclusion, nothing specific to sending) so neither file grows too large.

Clinic additions (marked ``# clinic``): ``hold_for_review`` / ``drop`` are the two other answers of
``PolicyHooks.on_outbound``. HOLD turns the text into a ``review_item`` (``followup_draft``) through
``AgentFacingClinicActions.create_review_item``, idempotent on ``<job id>@<scheduled instant>`` so a retry of
the same occurrence returns the same item; nothing is sent, no cap slot is taken (the slot is taken when a
human approves and the approved text goes out through ``PgProactiveSendGuard``), and the run is concluded
``ok`` ("draft handed to a person"). A failure to create the item counts as "nothing was handled" and goes
through ``conclude_delivery_failed`` like a failed send. DROP concludes the run ``skipped`` and spends the run
slot: the policy decided this occurrence must not exist, retrying it would only repeat the decision."""

from __future__ import annotations

import contextlib
from typing import Any

from pema.scheduler.deps import SchedulerDeps
from pema.scheduler.job_run_log_store import FinishRunParams
from pema.scheduler.ports import ReplyResult, ReplyTarget
from pema.scheduler.run_context import RunContext, decide_outbound
from pema.scheduler.scheduled_job_cap_guard import conclude_cap_blocked
from pema.scheduler.scheduled_job_conclude import (
    conclude,
    conclude_blocked_not_run,
    conclude_delivery_failed,
)
from pema.shared.logger import create_logger
from pema_contracts.actions import ActionContext, ActionSource
from pema_contracts.conversation import StoredMessage
from pema_contracts.policy import OutboundAction, OutboundOrigin
from pema_contracts.review import ReviewItemCreate, ReviewKind, ReviewOrigin, RiskLevel
from pema_contracts.roles import ActorType
from pema_contracts.scheduler import JobKind, JobOrigin, JobRunStatus

log = create_logger("run-scheduled-job")

REVIEW_DRAFT_MAX_CHARS = 4000
"""``ReviewItemCreate.draft_text`` maximum."""


async def blocked_by_guard(
    deps: SchedulerDeps, rc: RunContext, target: ReplyTarget, turn_id: int | None = None
) -> bool:
    """Check the guard RIGHT BEFORE SENDING: account/thread recheck FRESH (already checked at
    ``scheduler_loop`` before clear-before-dispatch, but an agent turn can run long) + TAKE 1 daily-cap slot
    ATOMICALLY (``reserve_proactive_slot``).

    When blocked it takes care of everything and returns ``True`` - the caller stops. ``False`` means 1 slot
    WAS TAKEN - the caller MUST call ``send_and_conclude`` right after."""
    job = rc.job
    fresh = await deps.guard.check_account_and_thread_ready(
        job.clinic_id, job.account_id, job.thread_id, rc.now
    )
    if not fresh.ok:
        await conclude_blocked_not_run(deps, job, rc.run_id, fresh.reason, rc.scheduled_for, turn_id)
        return True

    slot = await deps.guard.reserve_proactive_slot(
        job.clinic_id, rc.cap.scope_key, rc.time_zone, rc.now, rc.cap.max_per_day
    )
    if not slot.ok:
        await conclude_cap_blocked(
            deps,
            job,
            rc.run_id,
            slot.reason,
            rc.time_zone,
            rc.now,
            cap=rc.cap,
            ctx=rc.policy,
            notify_cap_hit_once=slot.notify_cap_hit_once,
            target=target,
            turn_id=turn_id,
        )
        return True

    return False


def _error_text(err: BaseException | None) -> str | None:
    if err is None:
        return None
    return str(err) or type(err).__name__


async def send_and_conclude(
    deps: SchedulerDeps,
    rc: RunContext,
    target: ReplyTarget,
    text: str,
    turn_id: int | None = None,
) -> None:
    """Send + write history + count the cap + close the run - ONE step, through ``deliver_proactively``.
    MUST be called AFTER ``blocked_by_guard`` returned ``False``; ``rc.now`` is EXACTLY the instant
    ``blocked_by_guard`` used to take the slot - one day off and the refund goes to the wrong day and the
    slot taken can never be claimed back.

    Sent (even only a part) -> the slot taken counts as USED - add the REST if ``sent_parts`` > 1. NOTHING
    could be sent -> give the slot back, then count it into ``delivery_attempts``
    (``conclude_delivery_failed``) - a failed send must not kill the job at once (Finding 1).

    FROM THE MOMENT ``reply.delivered_text`` is non-empty (Item 2, round 3): the message HAS LEFT, NO PATH may
    fall into ``conclude_delivery_failed`` any more - however the history write or the closing of the books
    fails. The earlier version let errors at THOSE steps propagate (no separate try/except), the catch of
    ``run_scheduled_job`` mistook them for "not sent" and RETRIED - sending the SAME content up to 3 times
    although the first message had arrived."""
    job = rc.job

    async def send() -> ReplyResult:
        # Translate markdown RIGHT AT sending, no earlier: the text written to history below must equal the
        # text the user sees on Zalo.
        plain_text, styles = deps.outbound.format_if_enabled(text)
        reply = await deps.outbound.send_reply_in_parts(target, plain_text, styles)
        if reply.delivered_text:
            try:
                await deps.history.append_message(
                    job.clinic_id,
                    job.account_id,
                    job.thread_id,
                    StoredMessage(role="assistant", content=reply.delivered_text),
                )
            except Exception as err:
                # The message ALREADY left - a failed history write must NOT turn "sent" into "not sent".
                # Attach it to ``reply.error`` (if there is no higher-priority error yet) so the branch below
                # still treats it as DELIVERED but writes the run as 'error' for the dashboard to see.
                log.error("Ghi history sau khi gửi thành công bị lỗi", job_id=job.id, err=err)
                if reply.error is None:
                    reply.error = err
        return reply

    reply = await deps.queue.deliver_proactively(job.clinic_id, job.account_id, job.thread_id, send)

    if not reply.delivered_text:
        await deps.guard.refund_proactive_slot(job.clinic_id, rc.cap.scope_key, rc.time_zone, rc.now)
        await conclude_delivery_failed(
            deps,
            job,
            rc.run_id,
            rc.scheduled_for,
            _error_text(reply.error) or "Gửi thất bại không rõ nguyên nhân.",
            turn_id,
        )
        return

    try:
        if reply.sent_parts > 1:
            await deps.guard.record_proactive_send(
                job.clinic_id, rc.cap.scope_key, rc.time_zone, reply.sent_parts - 1, rc.now
            )
        await _conclude_delivered(deps, rc, reply, turn_id)
    except Exception as err:
        await _conclude_post_send_bookkeeping_failed(deps, rc, reply, err, turn_id)


async def _conclude_delivered(
    deps: SchedulerDeps, rc: RunContext, reply: ReplyResult, turn_id: int | None
) -> None:
    """Close the run when it is CERTAIN the send succeeded - status per ``reply.error`` (it may be the history
    write error attached above)."""
    if reply.error is not None:
        await conclude(
            deps,
            rc.job,
            rc.run_id,
            FinishRunParams(
                status=JobRunStatus.ERROR,
                turn_id=turn_id,
                detail=_error_text(reply.error) or "Lỗi không rõ nguyên nhân.",
                delivered_chars=len(reply.delivered_text),
            ),
        )
        return
    await conclude(
        deps,
        rc.job,
        rc.run_id,
        FinishRunParams(
            status=JobRunStatus.OK,
            turn_id=turn_id,
            detail="Đã gửi.",
            delivered_chars=len(reply.delivered_text),
        ),
    )


async def _conclude_post_send_bookkeeping_failed(
    deps: SchedulerDeps, rc: RunContext, reply: ReplyResult, err: BaseException, turn_id: int | None
) -> None:
    """The bookkeeping ITSELF failed RIGHT AFTER a successful send (Item 2, round 3) - it MUST ``mark_run``
    (without it ``next_run_at``, already set to NULL by clear-before-dispatch, stays still forever - a
    "zombie" job: enabled=true but no tick can pick it up again). A 2-layer safety net: if ``conclude`` fails
    too (extremely rare) a raw ``finish_run`` at least takes the run out of 'running'."""
    log.error(
        "Chốt sổ sau khi gửi thành công bị lỗi - ghi run 'error' + mark_run, KHÔNG retry",
        job_id=rc.job.id,
        err=err,
    )
    try:
        await conclude(
            deps,
            rc.job,
            rc.run_id,
            FinishRunParams(
                status=JobRunStatus.ERROR,
                turn_id=turn_id,
                detail=f"Gửi thành công nhưng chốt sổ lỗi: {_error_text(err) or 'không rõ'}",
                delivered_chars=len(reply.delivered_text),
            ),
        )
    except Exception as err2:
        log.error("conclude() cũng lỗi ở lưới đỡ cuối - chỉ còn finish_run thô", job_id=rc.job.id, err=err2)
        with contextlib.suppress(Exception):  # already tried everything; one logging error must not kill us
            await deps.runs.finish_run(
                rc.job.clinic_id,
                rc.run_id,
                FinishRunParams(
                    status=JobRunStatus.ERROR,
                    turn_id=turn_id,
                    detail="Gửi thành công nhưng chốt sổ lỗi liên tiếp 2 lớp.",
                ),
            )


# ------------------------------------------------------------------------------------------- clinic


def _review_origin(job_kind: JobKind, job_origin: JobOrigin) -> ReviewOrigin:
    if job_kind is JobKind.AGENT:
        return ReviewOrigin.SCHEDULED_AGENT
    if job_origin is JobOrigin.CRM_RULE:
        return ReviewOrigin.CRM_RULE
    return ReviewOrigin.POLICY


async def hold_for_review(
    deps: SchedulerDeps,
    rc: RunContext,
    text: str,
    *,
    template_key: str | None = None,
    reason: str | None = None,
    turn_id: int | None = None,
) -> None:  # clinic
    """``OutboundAction.HOLD_FOR_REVIEW``: the text becomes a ``review_item`` and a person decides. See the
    module docstring for what is and is not counted."""
    job = rc.job
    try:
        patient_code: str | None = None
        if job.patient_id is not None:
            patient = await deps.patients.get_patient_ref(job.clinic_id, job.patient_id)
            patient_code = None if patient is None else patient.code
        payload: dict[str, Any] = {
            "job_id": job.id,
            "job_kind": job.kind.value,
            "job_origin": job.origin.value,
            "account_id": job.account_id,
            "thread_id": job.thread_id,
            "thread_type": job.thread_type,
            "scheduled_for": rc.scheduled_for,
            "late": rc.late,
        }
        if template_key is not None:
            payload["template_key"] = template_key
        if reason or rc.policy_reason:
            payload["policy_reason"] = reason or rc.policy_reason
        request = ReviewItemCreate(
            job_id=rc.review_key or f"{job.id}@{rc.scheduled_for}",
            clinic_id=job.clinic_id,
            patient_ref=patient_code,
            kind=ReviewKind.FOLLOWUP_DRAFT,
            origin=_review_origin(job.kind, job.origin),
            draft_text=text[:REVIEW_DRAFT_MAX_CHARS],
            payload=payload,
            risk_level=RiskLevel.NORMAL,
        )
        await deps.clinic_actions.create_review_item(
            ActionContext(
                clinic_id=job.clinic_id,
                actor_type=ActorType.SCHEDULER,
                source=ActionSource.SCHEDULER,
                idempotency_key=request.job_id[:128],
            ),
            request,
        )
    except Exception as err:
        log.error("Tạo review item cho job lịch hẹn thất bại", job_id=job.id, err=err)
        await conclude_delivery_failed(
            deps,
            job,
            rc.run_id,
            rc.scheduled_for,
            f"Không tạo được mục chờ duyệt: {_error_text(err) or type(err).__name__}",
            turn_id,
        )
        return

    await conclude(
        deps,
        job,
        rc.run_id,
        FinishRunParams(
            status=JobRunStatus.OK,
            turn_id=turn_id,
            detail="Đã chuyển vào hàng chờ duyệt - chưa gửi cho khách.",
        ),
    )


async def route_outbound(
    deps: SchedulerDeps,
    rc: RunContext,
    target: ReplyTarget,
    text: str,
    origin: OutboundOrigin,
    *,
    template_key: str | None = None,
    turn_id: int | None = None,
) -> None:  # clinic
    """The ONE place a finished text leaves a scheduled run: ask the policy (``on_outbound``), then SEND
    (guard + slot + send), HOLD for review, or DROP. ``text`` already carries the "late" label when needed."""
    decision = await decide_outbound(deps, rc, text, origin)

    if decision.action is OutboundAction.HOLD_FOR_REVIEW:
        await hold_for_review(
            deps, rc, text, template_key=template_key, reason=decision.reason, turn_id=turn_id
        )
        return

    if decision.action is OutboundAction.DROP:
        await conclude(
            deps,
            rc.job,
            rc.run_id,
            FinishRunParams(
                status=JobRunStatus.SKIPPED,
                turn_id=turn_id,
                detail=decision.reason or "Chính sách chặn tin này - không gửi.",
            ),
        )
        return

    if await blocked_by_guard(deps, rc, target, turn_id):
        return
    await send_and_conclude(deps, rc, target, text, turn_id)
